import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi } from '@/test/api';
import { progressOut } from '@/test/scan';
import { ProgressPill } from './progress-pill';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

const P = messages.nav.progress;

function progress(completed: number, streak: number) {
  const base = progressOut();
  return {
    ...base,
    counts: { ...base.counts, completed },
    streak: { ...base.streak, current: streak },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  pathname.value = '/';
});

describe('ProgressPill', () => {
  it('shows the insights learned and the days in a row, and leads to the practice page', async () => {
    const api = mockApi({ 'GET /me/progress': { body: progress(12, 3) } });
    render(<ProgressPill />);

    const link = await screen.findByRole('link', { name: P.label(12, 3) });
    expect(link).toHaveAttribute('href', '/sky');
    expect(link).toHaveTextContent('12 بصيرة');
    expect(link).toHaveTextContent('3 أيام متتالية');
    const asked = api.requests.find((request) => request.url.includes('/me/progress'));
    expect(new URL(asked?.url as string).searchParams.get('tz')).toBeTruthy();
  });

  it('says nothing of a streak that is not running, and counts in Arabic', async () => {
    mockApi({ 'GET /me/progress': { body: progress(2, 0) } });
    render(<ProgressPill />);
    const link = await screen.findByRole('link', { name: P.label(2, 0) });
    expect(link).toHaveTextContent('بصيرتان');
    expect(link).not.toHaveTextContent('متتالية');
    expect(P.streak(1)).toBe('يوم واحد متتالية');
    expect(P.streak(2)).toBe('يومان متتالية');
    expect(P.streak(11)).toBe('11 يومًا متتالية');
  });

  it('is absent before the first insight and when the API does not answer', async () => {
    const api = mockApi({ 'GET /me/progress': { body: progress(0, 0) } });
    const { container, unmount } = render(<ProgressPill />);
    await waitFor(() => expect(api.requests).toHaveLength(1));
    expect(container).toBeEmptyDOMElement();
    unmount();
    mockApi({ 'GET /me/progress': apiError(503, 'SERVICE_UNAVAILABLE') });
    const failed = render(<ProgressPill />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(failed.container).toBeEmptyDOMElement();
  });

  it('reads again on a new page, ignores an answer that comes after it left, and falls back to UTC', async () => {
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(() => {
      throw new RangeError('no zone');
    });
    const api = mockApi({ 'GET /me/progress': { body: progress(5, 1) } });
    const { rerender, unmount } = render(<ProgressPill />);
    await screen.findByRole('link');
    expect(new URL(api.requests[0]?.url as string).searchParams.get('tz')).toBe('UTC');
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(
      () => ({ resolvedOptions: () => ({ timeZone: '' }) }) as unknown as Intl.DateTimeFormat
    );
    pathname.value = '/world';
    rerender(<ProgressPill />);
    await waitFor(() => expect(api.requests).toHaveLength(2));
    expect(new URL(api.requests[1]?.url as string).searchParams.get('tz')).toBe('UTC');
    pathname.value = '/me';
    rerender(<ProgressPill />);
    unmount();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(api.requests).toHaveLength(3);
  });
});
