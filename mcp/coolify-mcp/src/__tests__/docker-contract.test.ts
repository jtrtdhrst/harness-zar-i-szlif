import { readFileSync } from 'node:fs';

describe('owned Coolify MCP Docker contract', () => {
  const dockerfile = readFileSync('Dockerfile', 'utf8');

  it('exposes the production MCP_PORT=8080 listener', () => {
    expect(dockerfile).toMatch(/^EXPOSE 8080$/m);
  });

  it('runs with existing OAuth /data volume UID 1000', () => {
    expect(dockerfile).toMatch(/^USER node$/m);
    expect(dockerfile).toContain('--chown=node:node');
  });
});
