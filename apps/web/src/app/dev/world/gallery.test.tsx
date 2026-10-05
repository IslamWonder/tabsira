import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import DevWorldPage, { metadata } from './page.dev';

/** The gallery renders inside the app's shell, which gives every «صوّر مشهدًا» its camera. */
function gallery() {
  return render(
    <CaptureProvider>
      <DevWorldPage />
    </CaptureProvider>
  );
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/dev/world',
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

describe('the world and practice gallery', () => {
  it('keeps out of search engines and shows each state in both themes, as inert pictures', () => {
    gallery();
    expect(metadata.robots).toEqual({ index: false, follow: false });
    const frames = Array.from(document.querySelectorAll<HTMLElement>('[data-viewport]'));
    // 4 states × 2 sizes × 2 themes.
    expect(frames).toHaveLength(16);
    expect(frames.every((frame) => frame.hasAttribute('inert'))).toBe(true);
    expect(screen.getByRole('region', { name: 'المظهر الداكن' })).toBeInTheDocument();
  });

  it('shows a newcomer clouds and the invitation, and a learner «بصائري»', () => {
    gallery();
    const phases = Array.from(document.querySelectorAll('[data-phase]')).map((frame) =>
      frame.getAttribute('data-phase')
    );
    expect(new Set(phases)).toEqual(new Set(['ready-progress', 'ready-empty']));
    expect(screen.getAllByText('كلّ بصيرة تفتح أفقًا.')).toHaveLength(4);
    expect(screen.getAllByRole('button', { name: 'بصائري', hidden: true })).toHaveLength(4);
  });
});
