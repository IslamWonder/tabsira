// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publicInsightOut } from '@/test/share';

const renderCard = vi.fn();
vi.mock('./render', () => ({ renderCard }));

async function service() {
  vi.resetModules();
  return import('./service');
}

beforeEach(() => {
  renderCard.mockReset();
});

describe('the card of an insight', () => {
  it('draws a card once and answers the same content from memory', async () => {
    renderCard.mockResolvedValue(Buffer.from('png'));
    const { cardPng } = await service();
    const insight = publicInsightOut();
    expect((await cardPng(insight, 'tabsira.me')).toString()).toBe('png');
    expect((await cardPng(publicInsightOut(), 'tabsira.me')).toString()).toBe('png');
    expect(renderCard).toHaveBeenCalledTimes(1);
    await cardPng(publicInsightOut({ title: 'عنوان آخر' }), 'tabsira.me');
    await cardPng(insight, 'tabsira.test');
    expect(renderCard).toHaveBeenCalledTimes(3);
  });

  it('draws two cards at a time, queues four and refuses the rest', async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderCard.mockImplementation(async () => {
      await held;
      return Buffer.from('png');
    });
    const { cardPng } = await service();
    const { Busy } = await import('./limiter');
    const calls = Array.from({ length: 7 }, (_, index) =>
      cardPng(publicInsightOut({ title: `عنوان ${index}` }), 'tabsira.me').then(
        () => 'drawn',
        (error: unknown) => (error instanceof Busy ? 'busy' : 'failed')
      )
    );
    await vi.waitFor(() => expect(renderCard).toHaveBeenCalledTimes(2));
    release();
    expect(await Promise.all(calls)).toEqual([
      'drawn',
      'drawn',
      'drawn',
      'drawn',
      'drawn',
      'drawn',
      'busy',
    ]);
  });

  it('does not remember a card that failed to draw', async () => {
    renderCard.mockRejectedValueOnce(new Error('no'));
    renderCard.mockResolvedValue(Buffer.from('png'));
    const { cardPng } = await service();
    await expect(cardPng(publicInsightOut(), 'tabsira.me')).rejects.toThrow('no');
    expect((await cardPng(publicInsightOut(), 'tabsira.me')).toString()).toBe('png');
  });
});
