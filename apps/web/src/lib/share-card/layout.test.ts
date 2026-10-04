import { describe, expect, it } from 'vitest';
import { blockSizes, candidates, columnWidth, GROWING, TALL, WIDE } from './layout';

describe('the shapes of a card', () => {
  it('tries the wide card, then the tall one, then the verse alone; a card that grows is the last resort', () => {
    const list = candidates(true);
    expect(list.slice(0, 5).map((c) => [c.shape.name, c.scale, c.hadith])).toEqual([
      ['wide', 1, true],
      ['wide', 0.85, true],
      ['tall', 1, true],
      ['tall', 0.85, true],
      ['tall', 0.7, true],
    ]);
    expect(list).toHaveLength(10);
    expect(list.slice(5).every((c) => !c.hadith)).toBe(true);
    expect(GROWING).toMatchObject({ shape: TALL, hadith: false });
  });

  it('skips the attempts with a hadith when there is none', () => {
    const list = candidates(false);
    expect(list).toHaveLength(5);
    expect(list.some((c) => c.hadith)).toBe(false);
  });

  it('scales the sizes of the texts with the candidate', () => {
    expect(blockSizes({ shape: WIDE, scale: 1, hadith: true })).toEqual({
      verse: 38,
      hadith: 28,
    });
    expect(blockSizes({ shape: TALL, scale: 0.7, hadith: true })).toEqual({
      verse: 29,
      hadith: 22,
    });
  });

  it('leaves a column inside the padding', () => {
    expect(columnWidth(WIDE)).toBe(1200 - 2 * 44);
  });
});
