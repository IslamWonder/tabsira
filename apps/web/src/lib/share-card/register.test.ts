// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { publicInsightOut } from '@/test/share';

const drawText = vi.fn();
vi.mock('./text-image', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./text-image')>();
  return {
    ...actual,
    drawText: (...args: Parameters<typeof actual.drawText>) => drawText(...args),
  };
});

describe('registering the faces', () => {
  it('is tried again on the next card after a failure, not kept for good', async () => {
    const { drawText: actual } =
      await vi.importActual<typeof import('./text-image')>('./text-image');
    drawText.mockRejectedValueOnce(new Error('engine not ready'));
    drawText.mockImplementation(actual);
    const { renderCard } = await import('./render');
    await expect(renderCard(publicInsightOut(), 'tabsira.test')).rejects.toThrow(
      'engine not ready'
    );
    const png = await renderCard(publicInsightOut(), 'tabsira.test');
    expect(png.subarray(1, 4).toString()).toBe('PNG');
  });
});
