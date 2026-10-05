import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { mockApi } from '@/test/api';
import { PLACE_ONE } from '@/test/world';
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

// The pictures of the stage are not decoded in a test: the landmarks draw once they "load".
vi.mock('@/components/world/world-pictures', () => ({
  LANDSCAPE_SRC: '/world/landscape-1.webp',
  CLOUDS_SRC: '/world/clouds-1.webp',
  loadPicture: () => Promise.resolve({}),
}));

function fakeContext() {
  const gradient = { addColorStop: vi.fn() };
  return {
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => gradient),
    createLinearGradient: vi.fn(() => gradient),
  };
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1440);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(828);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => fakeContext() as unknown as RenderingContext
  );
});

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

  it('lets a place be opened on the sample data, whose visit changes nothing', async () => {
    const api = mockApi({ 'POST /world/places/7001/visit': { body: PLACE_ONE } });
    gallery();
    const [landmark] = await screen.findAllByText('[موضع أول]');
    fireEvent.click(landmark as HTMLElement);
    await waitFor(() =>
      expect(api.requests.map((request) => new URL(request.url).pathname)).toContain(
        '/world/places/7001/visit'
      )
    );
  });
});
