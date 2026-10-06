import { describe, expect, it } from 'vitest';
import { LIGHT_OFFSET, placeStars, type StarSize, spiral } from './sky-layout';

const FIELD = { width: 1000, height: 500 };

function star(key: string, x: number, y: number, width = 80, height = 70): StarSize {
  return { key, x, y, width, height };
}

describe('placeStars', () => {
  it('keeps every star at the place its name gives it while that place is free', () => {
    const { placed, unplaced } = placeStars([star('أ', 0.2, 0.3), star('ب', 0.7, 0.6)], FIELD, []);
    expect(placed.get('أ')).toEqual({ x: 200, y: 150 });
    expect(placed.get('ب')).toEqual({ x: 700, y: 300 });
    expect(unplaced).toEqual([]);
  });

  it('moves the newer of two stars that land on each other, never the older one', () => {
    const before = placeStars([star('قديم', 0.5, 0.5)], FIELD, []);
    const after = placeStars([star('قديم', 0.5, 0.5), star('جديد', 0.5, 0.5)], FIELD, []);
    expect(after.placed.get('قديم')).toEqual(before.placed.get('قديم'));
    const moved = after.placed.get('جديد');
    expect(moved).toBeDefined();
    expect(moved).not.toEqual({ x: 500, y: 250 });
    // Their boxes no longer touch.
    const dx = Math.abs((moved?.x ?? 0) - 500);
    const dy = Math.abs((moved?.y ?? 0) - 250);
    expect(dx >= 80 || dy >= 70).toBe(true);
  });

  it('lays the same stars out the same way every time', () => {
    const stars = [star('أ', 0.4, 0.4), star('ب', 0.41, 0.41), star('ج', 0.42, 0.39)];
    expect(placeStars(stars, FIELD, [])).toEqual(placeStars(stars, FIELD, []));
  });

  it('keeps clear of the heading and the dock', () => {
    const heading = { x: 700, y: 0, width: 300, height: 120 };
    const { placed } = placeStars([star('أ', 0.85, 0.1)], FIELD, [heading]);
    const at = placed.get('أ');
    expect(at).toBeDefined();
    const top = (at?.y ?? 0) - LIGHT_OFFSET;
    const left = (at?.x ?? 0) - 40;
    const clear = top >= heading.y + heading.height || left + 80 <= heading.x;
    expect(clear).toBe(true);
  });

  it('keeps a star wholly inside the field, its name included', () => {
    const { placed } = placeStars([star('أ', 0.99, 0.99)], FIELD, []);
    const at = placed.get('أ');
    expect((at?.x ?? 0) + 40).toBeLessThanOrEqual(FIELD.width);
    expect((at?.y ?? 0) - LIGHT_OFFSET + 70).toBeLessThanOrEqual(FIELD.height);
  });

  it('leaves out a star with no free place, for the list of all meanings to hold', () => {
    const tiny = { width: 90, height: 80 };
    const { placed, unplaced } = placeStars([star('أ', 0.5, 0.5), star('ب', 0.5, 0.5)], tiny, []);
    expect([...placed.keys()]).toEqual(['أ']);
    expect(unplaced).toEqual(['ب']);
  });
});

describe('a full field', () => {
  it('stops searching after a few stars in a row found no place, sending the rest to the list', () => {
    const tiny = { width: 90, height: 80 };
    const stars = Array.from({ length: 8 }, (_, index) => star(String(index), 0.5, 0.5));
    const { placed, unplaced } = placeStars(stars, tiny, []);
    expect([...placed.keys()]).toEqual(['0']);
    expect(unplaced).toEqual(['1', '2', '3', '4', '5', '6', '7']);
  });

  it('counts the misses afresh after a star that fits', () => {
    const field = { width: 400, height: 80 };
    const narrow = (key: string, x: number) => star(key, x, 0.5, 60, 70);
    const wide = (key: string) => star(key, 0.5, 0.5, 390, 70);
    const { placed, unplaced } = placeStars(
      [
        narrow('1', 0.1),
        wide('w1'),
        wide('w2'),
        wide('w3'),
        narrow('2', 0.5),
        wide('w4'),
        wide('w5'),
        wide('w6'),
        // Six misses in all, but never four in a row: this star is still searched for, and fits.
        narrow('3', 0.9),
      ],
      field,
      []
    );
    expect([...placed.keys()]).toEqual(['1', '2', '3']);
    expect(unplaced).toEqual(['w1', 'w2', 'w3', 'w4', 'w5', 'w6']);
  });
});

describe('spiral', () => {
  it('tries the place itself first, then rings around it', () => {
    const points = spiral(10, 20);
    expect(points.next().value).toEqual([10, 20]);
    const [x, y] = points.next().value as [number, number];
    expect(Math.hypot(x - 10, y - 20)).toBeCloseTo(14);
  });
});
