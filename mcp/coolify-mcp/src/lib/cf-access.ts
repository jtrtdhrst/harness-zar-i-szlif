/**
 * Cloudflare Access Managed OAuth: Access authenticates the user at the edge
 * and forwards a signed `Cf-Access-Jwt-Assertion`. The origin must verify that
 * assertion itself; trusting the header without a signature check would let a
 * direct-to-origin request impersonate any user.
 *
 * Configured by `CF_ACCESS_ISSUER` + `CF_ACCESS_AUD` (the Access application's
 * AUD tag). Both or neither: a half-set pair is a startup error, and when the
 * pair is absent the legacy local OAuth flow is unchanged.
 */

import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from 'jose';

export interface CfAccessConfig {
  /** Cloudflare team domain, e.g. https://team.cloudflareaccess.com */
  issuer: string;
  /** The Access application's AUD tag. */
  audience: string;
}

export interface CfAccessIdentity {
  subject: string;
  email?: string;
}

/** An assertion is a few KB; anything larger is not a Cloudflare token. */
const MAX_ASSERTION_BYTES = 16 * 1024;
/** Cloudflare's own guidance: tolerate small clock skew between edge and origin. */
const CLOCK_TOLERANCE_SECONDS = 15;

/**
 * Read the pair from the environment. Returns undefined when neither is set;
 * callers run `checkStartupConfig` first, which rejects a half-set pair.
 */
export function cfAccessConfigFromEnv(env: NodeJS.ProcessEnv): CfAccessConfig | undefined {
  const issuer = env.CF_ACCESS_ISSUER?.trim();
  const audience = env.CF_ACCESS_AUD?.trim();
  if (!issuer || !audience) return undefined;
  return { issuer: issuer.replace(/\/+$/, ''), audience };
}

/**
 * Build the verifier. `jwks` is injectable so tests can use a local key set;
 * production uses Cloudflare's published certs at `<issuer>/cdn-cgi/access/certs`.
 */
export function createCfAccessVerifier(
  config: CfAccessConfig,
  jwks: JWTVerifyGetKey = createRemoteJWKSet(
    new URL(`${config.issuer.replace(/\/+$/, '')}/cdn-cgi/access/certs`),
  ),
): (assertion: string) => Promise<CfAccessIdentity> {
  return async (assertion) => {
    if (new TextEncoder().encode(assertion).byteLength > MAX_ASSERTION_BYTES) {
      throw new Error('Cloudflare Access assertion is too large');
    }
    const { payload } = await jwtVerify(assertion, jwks, {
      issuer: config.issuer,
      audience: config.audience,
      algorithms: ['RS256'],
      clockTolerance: CLOCK_TOLERANCE_SECONDS,
      requiredClaims: ['exp', 'iss', 'aud', 'sub', 'iat'],
    });
    if (typeof payload.sub !== 'string' || payload.sub === '') {
      throw new Error('Cloudflare Access assertion has no subject');
    }
    return {
      subject: payload.sub,
      email: typeof payload.email === 'string' ? payload.email : undefined,
    };
  };
}
