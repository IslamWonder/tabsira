import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { RECORD } from '@/test/fixtures';
import { POST } from './route';

function post(fields: Record<string, string>, headers: Record<string, string> = {}) {
  return POST(
    new Request('https://tabsira.test/consent', {
      method: 'POST',
      headers: { Origin: 'https://tabsira.test', ...headers },
      body: new URLSearchParams(fields),
    })
  );
}

function cookies(response: Response): string[] {
  return response.headers.getSetCookie();
}

describe('POST /consent, the cookie choice without JavaScript', () => {
  it('records a choice through the API, keeps the id and goes back', async () => {
    const api = mockApi({ 'POST /consent': { status: 201, body: RECORD } });
    const response = await post(
      { choice: 'accept', return: '/world', policy_version: '2026-10-04' },
      {
        'User-Agent': 'Test Browser',
        Cookie: `tabsira_consent=${RECORD.consent_id}; other=1`,
      }
    );
    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('https://tabsira.test/world');
    expect(cookies(response).find((line) => line.startsWith('tabsira_consent='))).toMatch(
      /tabsira_consent=c0ffee00-1234-4abc-9def-0123456789ab; Path=\/; .*Max-Age=34128000.*Secure.*SameSite=lax/i
    );
    expect(await api.bodies('POST', '/consent')).toEqual([
      {
        consent_id: RECORD.consent_id,
        policy_version: '2026-10-04',
        necessary: true,
        analytics: true,
        behaviour: true,
      },
    ]);
    const sent = api.requests[0] as Request;
    expect(sent.headers.get('user-agent')).toBe('Test Browser');
    expect(sent.headers.get('cookie')).toContain('tabsira_consent=');
  });

  it('saves the categories a customised form ticked', async () => {
    const api = mockApi({ 'POST /consent': { status: 201, body: RECORD } });
    await post({ choice: 'save', return: '/', behaviour: 'on' });
    expect(await api.bodies('POST', '/consent')).toEqual([
      { necessary: true, analytics: false, behaviour: true },
    ]);
  });

  it('opens the customise view, and goes back to the summary', async () => {
    const customise = await post({ choice: 'customise', return: '/me' });
    expect(cookies(customise)[0]).toMatch(
      /^tabsira_consent_view=customise; Path=\/; .*Max-Age=300; Secure; SameSite=lax/
    );
    const back = await post({ choice: 'back', return: '/me' });
    expect(cookies(back)[0]).toMatch(/^tabsira_consent_view=; Path=\/; Max-Age=0/);
  });

  it('closes on a refusal the API could not record, and forgets an earlier yes', async () => {
    mockApi({ 'POST /consent': 'network-error' });
    const response = await post({ choice: 'reject', return: '//evil.example' });
    expect(response.headers.get('location')).toBe('https://tabsira.test/me');
    const set = cookies(response).join('\n');
    expect(set).toMatch(/tabsira_consent=; Path=\/; Max-Age=0/);
    expect(set).toMatch(/tabsira_consent_dismissed=1; Path=\//);
  });

  it('shows the failure when a yes could not be recorded', async () => {
    mockApi({ 'POST /consent': apiError(429, 'RATE_LIMITED') });
    const response = await post({ choice: 'accept' });
    expect(response.headers.get('location')).toBe('https://tabsira.test/');
    expect(cookies(response).join('\n')).toMatch(
      /tabsira_consent_view=failed; Path=\/; .*Max-Age=300/
    );
  });

  it('refuses another site, and a choice it does not know', async () => {
    expect((await post({ choice: 'accept' }, { Origin: 'https://evil.example' })).status).toBe(403);
    expect((await post({ choice: 'everything' })).status).toBe(400);
    const sameSite = await POST(
      new Request('https://tabsira.test/consent', {
        method: 'POST',
        headers: { 'Sec-Fetch-Site': 'cross-site' },
        body: new URLSearchParams({ choice: 'accept' }),
      })
    );
    expect(sameSite.status).toBe(403);
  });
});
