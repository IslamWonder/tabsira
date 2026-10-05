import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { messages } from '@/messages';
import DevSkyPage, { metadata } from './page.dev';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  usePathname: () => '/dev/sky',
}));

const M = messages.practiceView.sky;

async function page(state?: string) {
  const node = await DevSkyPage({ searchParams: Promise.resolve(state ? { state } : {}) });
  return render(<CaptureProvider>{node}</CaptureProvider>);
}

describe('the sky preview page', () => {
  it('keeps out of search engines and shows the reference meanings by default', async () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
    await page();
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);
    expect(screen.getByRole('button', { name: /^الرحمة/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(M.count(8))).toBeInTheDocument();
  });

  it.each([
    ['empty', M.emptyTitle],
    ['loading', M.loading],
    ['failed', M.unavailable],
  ])('shows the %s state', async (state, text) => {
    await page(state);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('offers a retry in the failure state that does nothing on sample data', async () => {
    await page('failed');
    screen.getByRole('button', { name: messages.practiceView.retry }).click();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
