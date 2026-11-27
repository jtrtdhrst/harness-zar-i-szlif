/**
 * Cloudflare Access Managed OAuth (#...): assertion verification and the
 * /mcp gate. The positive HTTP case uses a real local JWKS endpoint so the
 * production `createRemoteJWKSet` path is exercised, not a mock.
 */

import { describe, it, expect, beforeAll, afterAll } from '@jest/globals';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import {
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  SignJWT,
  type JWK,
  type KeyLike,
} from 'jose';
import { cfAccessConfigFromEnv, createCfAccessVerifier } from '../lib/cf-access.js';
import { createHttpApp } from '../lib/http-server.js';

const ISSUER = 'https://mcp.example.com';
const RESOURCE = `${ISSUER}/mcp`;
const AUDIENCE = 'aud-tag-123';

async function keyMaterial(): Promise<{
  privateKey: KeyLike;
  jwk: JWK;
}> {
  const { publicKey, privateKey } = await generateKeyPair('RS256');
  const jwk = await exportJWK(publicKey);
  jwk.kid = 'test-key';
  jwk.alg = 'RS256';
  jwk.use = 'sig';
  return { privateKey, jwk };
}

async function sign(
  privateKey: KeyLike,
  overrides: {
    issuer?: string;
    audience?: string;
    expiresIn?: string;
    subject?: string;
    email?: string;
  } = {},
): Promise<string> {
  return new SignJWT({ email: overrides.email ?? 'owner@example.com' })
    .setProtectedHeader({ alg: 'RS256', kid: 'test-key' })
    .setIssuer(overrides.issuer ?? 'https://team.cloudflareaccess.com')
    .setAudience(overrides.audience ?? AUDIENCE)
    .setSubject(overrides.subject ?? 'user-1')
    .setIssuedAt()
    .setExpirationTime(overrides.expiresIn ?? '5m')
    .sign(privateKey);
}

describe('cfAccessConfigFromEnv', () => {
  it('returns undefined unless both variables are set', () => {
    expect(cfAccessConfigFromEnv({})).toBeUndefined();
    expect(
      cfAccessConfigFromEnv({ CF_ACCESS_ISSUER: 'https://team.cloudflareaccess.com' }),
    ).toBeUndefined();
    expect(cfAccessConfigFromEnv({ CF_ACCESS_AUD: AUDIENCE })).toBeUndefined();
  });

  it('trims the pair and removes a trailing slash from the issuer', () => {
    expect(
      cfAccessConfigFromEnv({
        CF_ACCESS_ISSUER: ' https://team.cloudflareaccess.com/ ',
        CF_ACCESS_AUD: ` ${AUDIENCE} `,
      }),
    ).toEqual({ issuer: 'https://team.cloudflareaccess.com', audience: AUDIENCE });
  });
});

describe('createCfAccessVerifier', () => {
  it('accepts a correctly signed assertion and returns the identity', async () => {
    const { privateKey, jwk } = await keyMaterial();
    const verify = createCfAccessVerifier(
      { issuer: 'https://team.cloudflareaccess.com', audience: AUDIENCE },
      createLocalJWKSet({ keys: [jwk] }),
    );
    await expect(verify(await sign(privateKey))).resolves.toEqual({
      subject: 'user-1',
      email: 'owner@example.com',
    });
  });

  it('rejects a wrong audience, wrong issuer, and expired assertion', async () => {
    const { privateKey, jwk } = await keyMaterial();
    const verify = createCfAccessVerifier(
      { issuer: 'https://team.cloudflareaccess.com', audience: AUDIENCE },
      createLocalJWKSet({ keys: [jwk] }),
    );
    await expect(verify(await sign(privateKey, { audience: 'other-aud' }))).rejects.toThrow();
    await expect(
      verify(await sign(privateKey, { issuer: 'https://evil.cloudflareaccess.com' })),
    ).rejects.toThrow();
    await expect(verify(await sign(privateKey, { expiresIn: '-1m' }))).rejects.toThrow();
  });

  it('rejects an assertion larger than the 16 KiB cap before parsing', async () => {
    const { privateKey, jwk } = await keyMaterial();
    const verify = createCfAccessVerifier(
      { issuer: 'https://team.cloudflareaccess.com', audience: AUDIENCE },
      createLocalJWKSet({ keys: [jwk] }),
    );
    await expect(verify('x'.repeat(16 * 1024 + 1))).rejects.toThrow(/too large/);
    // The key material is still valid; this only proves the size gate fires
    // before jwtVerify would try to parse the blob.
    expect(privateKey).toBeDefined();
  });
});

describe('createHttpApp with Cloudflare Access', () => {
  const server = createServer((req, res) => {
    if (req.url === '/cdn-cgi/access/certs') {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ keys: [jwk] }));
      return;
    }
    res.writeHead(404);
    res.end();
  });
  let jwk: JWK;
  let privateKey: KeyLike;
  let issuer = '';
  let app: ReturnType<typeof createHttpApp>;

  beforeAll(async () => {
    const material = await keyMaterial();
    jwk = material.jwk;
    privateKey = material.privateKey;
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const { port } = server.address() as AddressInfo;
    issuer = `http://127.0.0.1:${port}`;
    app = createHttpApp({
      coolify: { baseUrl: 'https://coolify.example.com', accessToken: 'env-token' },
      publicUrl: ISSUER,
      accessTokenTtl: 3600,
      refreshTokenTtl: 28_800,
      stateFile: '',
      readonly: false,
      cfAccess: { issuer, audience: AUDIENCE },
    });
  });

  afterAll(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  function initializeRequest(headers: Record<string, string> = {}): Request {
    return new Request(RESOURCE, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
        ...headers,
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: '2025-03-26',
          capabilities: {},
          clientInfo: { name: 'cf-access-test', version: '1' },
        },
      }),
    });
  }

  it('challenges a request with no assertion and points at Cloudflare metadata', async () => {
    const response = await app.fetch(initializeRequest());
    expect(response.status).toBe(401);
    const challenge = response.headers.get('www-authenticate') ?? '';
    expect(challenge).toContain(
      `resource_metadata="${ISSUER}/.well-known/cloudflare-access-protected-resource/mcp"`,
    );
  });

  it('refuses the legacy local bearer token once Cloudflare Access is configured', async () => {
    const response = await app.fetch(
      initializeRequest({ authorization: 'Bearer mcp_at_not_a_real_token' }),
    );
    expect(response.status).toBe(401);
  });

  it('refuses an assertion that fails verification', async () => {
    const response = await app.fetch(initializeRequest({ 'cf-access-jwt-assertion': 'not.a.jwt' }));
    expect(response.status).toBe(401);
    expect(response.headers.get('www-authenticate')).toContain('error="invalid_token"');
  });

  it('accepts a valid assertion and reaches the MCP handler', async () => {
    const token = await sign(privateKey, { issuer, audience: AUDIENCE });
    const response = await app.fetch(initializeRequest({ 'cf-access-jwt-assertion': token }));
    expect(response.status).not.toBe(401);
    expect(response.status).toBe(200);
  });
});
