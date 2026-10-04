import { vi } from 'vitest';

/*
 * Unit tests never reach the network (AGENTS.md). src/test/setup.ts replaces
 * fetch with one that never answers; a test that needs the API describes the
 * answers it expects here, by method and path, and nothing else is served.
 */

export interface Reply {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export type Route = Reply | ((request: Request) => Reply | Promise<Reply>) | 'network-error';

export interface ApiMock {
  /** Every request made, in order. */
  requests: Request[];
  /** The JSON bodies sent, in order, for the requests that had one. */
  bodies(method: string, path: string): Promise<unknown[]>;
}

export const NEVER_ANSWERS = () => new Promise<Response>(() => undefined);

function respond({ status = 200, body, headers = {} }: Reply): Response {
  if (status === 204 || body === undefined) {
    return new Response(null, { status, headers });
  }
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/** An API error answer, in the API's own shape. */
export function apiError(
  status: number,
  error: string,
  extra: Record<string, unknown> = {}
): Reply {
  return { status, body: { error, detail: 'test', ...extra } };
}

/**
 * Serves `routes` (keys like "GET /auth/me", matched on the path without the
 * query) and fails loudly on anything else. Returns the requests for checks.
 */
export function mockApi(routes: Record<string, Route>): ApiMock {
  const requests: Request[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    requests.push(request.clone());
    const url = new URL(request.url);
    const route = routes[`${request.method} ${url.pathname}`];
    if (route === undefined) {
      throw new Error(`unexpected request in a unit test: ${request.method} ${url.pathname}`);
    }
    if (route === 'network-error') {
      throw new TypeError('Failed to fetch');
    }
    return respond(typeof route === 'function' ? await route(request) : route);
  });
  vi.stubGlobal('fetch', fetch);
  return {
    requests,
    async bodies(method, path) {
      const matching = requests.filter(
        (request) => request.method === method && new URL(request.url).pathname === path
      );
      return Promise.all(matching.map((request) => request.clone().json() as Promise<unknown>));
    },
  };
}
