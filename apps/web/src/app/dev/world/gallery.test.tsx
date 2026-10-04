import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { PLACE_ONE } from '@/test/world';
import DevWorldPage, { metadata } from './page.dev';

vi.mock('next/navigation', () => ({ usePathname: () => '/dev/world' }));

describe('the world and practice gallery', () => {
  it('keeps out of search engines and shows each state in both themes, as inert pictures', () => {
    render(<DevWorldPage />);
    expect(metadata.robots).toEqual({ index: false, follow: false });
    const frames = Array.from(document.querySelectorAll<HTMLElement>('[data-viewport]'));
    // 5 states × 2 sizes × 2 themes.
    expect(frames).toHaveLength(20);
    expect(frames.every((frame) => frame.hasAttribute('inert'))).toBe(true);
    expect(screen.getByRole('region', { name: 'المظهر الداكن' })).toBeInTheDocument();
  });

  it('opens a region on sample data, and records the visit like the real screen', async () => {
    const api = mockApi({ 'POST /world/places/7001/visit': { body: PLACE_ONE } });
    render(<DevWorldPage />);
    const button = document.querySelector<HTMLButtonElement>('[data-region="T00"]');
    fireEvent.click(button as HTMLButtonElement);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(api.requests).toHaveLength(1));
    // Let the answer reach the screen's handler.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  });
});
