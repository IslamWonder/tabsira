import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { loadGoogleAvailable, useGoogleAvailable } from './providers';

function Probe() {
  return <p>{String(useGoogleAvailable())}</p>;
}

const providers = (google: boolean) => ({
  body: {
    providers: [
      { id: 'password', available: true },
      { id: 'google', available: google },
    ],
  },
});

describe('Google availability', () => {
  it('is unknown, then what /auth/providers says, asked once', async () => {
    const api = mockApi({ 'GET /auth/providers': providers(true) });
    render(<Probe />);
    expect(screen.getByText('null')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('true')).toBeInTheDocument());
    expect(await loadGoogleAvailable()).toBe(true);
    expect(api.requests).toHaveLength(1);
  });

  it('is off when Google is not configured, and when the API fails (asked again later)', async () => {
    mockApi({ 'GET /auth/providers': providers(false) });
    expect(await loadGoogleAvailable()).toBe(false);
  });

  it('asks again after a failure', async () => {
    const api = mockApi({ 'GET /auth/providers': apiError(503, 'SERVICE_UNAVAILABLE') });
    expect(await loadGoogleAvailable()).toBe(false);
    expect(await loadGoogleAvailable()).toBe(false);
    expect(api.requests).toHaveLength(2);
  });

  it('ignores an answer that arrives after the page moved on', async () => {
    mockApi({ 'GET /auth/providers': providers(true) });
    const { unmount } = render(<Probe />);
    unmount();
    expect(await loadGoogleAvailable()).toBe(true);
  });
});
