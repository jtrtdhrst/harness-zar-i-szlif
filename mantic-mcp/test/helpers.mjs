/**
 * Test doubles for the mantic-mcp tool layer.
 *
 * The handlers only touch `client.v1` / `client.v2`, `client.getBaseUrl()` and
 * `client.parseV2Collection()`, so a recording fake is enough to assert the
 * exact outbound method + path + body the provider would receive. No network.
 */
import { AxiosError } from 'axios';

/** Build an axios-compatible error so `axios.isAxiosError` handles it normally. */
export function axiosError(status, data = {}) {
  const error = new AxiosError(`Request failed with status code ${status}`);
  error.response = { status, data, headers: {}, config: {} };
  error.status = status;
  return error;
}

/** Return responses in order, repeating the last one when exhausted. */
export function sequence(responses) {
  let index = 0;
  return () => {
    const entry = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (entry instanceof Error) throw entry;
    return entry;
  };
}

export function mockClient({
  baseUrl = 'https://mautic.example.pl/api/',
  accessToken = 'ACCESS-TOKEN-SHOULD-NEVER-LEAK',
  clientSecret = 'CLIENT-SECRET-SHOULD-NEVER-LEAK',
  routes = {},
} = {}) {
  const calls = [];

  const resolve = (surface, method, path) => {
    const key = `${surface}:${method}:${path}`;
    const route = routes[key] ?? routes[`${surface}:${method}:*`];
    if (route === undefined) {
      throw new Error(`unexpected Mautic request: ${key}`);
    }
    if (route instanceof Error) throw route;
    return typeof route === 'function' ? route() : route;
  };

  const instance = (surface) => ({
    async get(path, config) {
      calls.push({ surface, method: 'GET', path, config });
      return resolve(surface, 'GET', path);
    },
    async post(path, body, config) {
      calls.push({ surface, method: 'POST', path, body, config });
      return resolve(surface, 'POST', path);
    },
    async patch(path, body, config) {
      calls.push({ surface, method: 'PATCH', path, body, config });
      return resolve(surface, 'PATCH', path);
    },
    async put(path, body, config) {
      calls.push({ surface, method: 'PUT', path, body, config });
      return resolve(surface, 'PUT', path);
    },
    async delete(path, config) {
      calls.push({ surface, method: 'DELETE', path, config });
      return resolve(surface, 'DELETE', path);
    },
  });

  return {
    calls,
    accessToken,
    clientSecret,
    v1: instance('v1'),
    v2: instance('v2'),
    getBaseUrl: () => baseUrl,
    parseV2Collection(data) {
      if (data?.['hydra:member']) {
        return {
          items: data['hydra:member'],
          total: data['hydra:totalItems'] ?? data['hydra:member'].length,
        };
      }
      return { items: Array.isArray(data) ? data : [data], total: 1 };
    },
  };
}
