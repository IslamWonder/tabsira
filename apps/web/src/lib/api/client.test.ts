import { describe, expect, it, vi } from 'vitest';
import { api, createApiClient } from './client';

describe('the API client', () => {
  it('calls the API origin with the session cookie', async () => {
    const fetch = vi.fn(
      async (_request: Request) =>
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
    );
    const client = createApiClient({ fetch });

    const { data, error } = await client.GET('/health');

    expect(error).toBeUndefined();
    expect(data).toEqual({ status: 'ok' });
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe('https://api.tabsira.test/health');
    expect(request.credentials).toBe('include');
  });

  it('keeps credentials on even when another base URL is given', async () => {
    const fetch = vi.fn(async (_request: Request) => new Response(null, { status: 204 }));
    await createApiClient({ baseUrl: 'https://api.tabsira.me', fetch }).GET('/health');
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe('https://api.tabsira.me/health');
    expect(request.credentials).toBe('include');
  });

  it('exports a ready client', () => {
    expect(typeof api.GET).toBe('function');
  });
});
