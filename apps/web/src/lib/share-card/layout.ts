import type { components } from '@/lib/api/schema';

/*
 * The shapes a card can take, and the order they are tried in. The one rule
 * that decides everything: scripture is shown whole or not at all, never cut.
 * The verse and the hadith are drawn first and measured; the card then takes
 * the first shape and size at which what was measured fits: the wide
 * link-preview card, the tall card, a smaller size, the verse alone (the hadith
 * is then left to the public page and the card says so) and, last, a tall card
 * as high as the verse needs (`GROWING`). The decision always rests on a measurement.
 */

export type PublicInsight = components['schemas']['PublicInsightOut'];

export interface CardShape {
  readonly name: 'wide' | 'tall';
  readonly width: number;
  readonly height: number;
  readonly padding: number;
  /** Body sizes at scale 1, in pixels. */
  readonly verseSize: number;
  readonly hadithSize: number;
}

/** 1200 x 630 is the link-preview shape; 1080 x 1350 carries long texts and suits a phone's share view. */
export const WIDE: CardShape = {
  name: 'wide',
  width: 1200,
  height: 630,
  padding: 44,
  verseSize: 38,
  hadithSize: 28,
};
export const TALL: CardShape = {
  name: 'tall',
  width: 1080,
  height: 1350,
  padding: 56,
  verseSize: 42,
  hadithSize: 32,
};

export interface Candidate {
  readonly shape: CardShape;
  readonly scale: number;
  readonly hadith: boolean;
}

const SCALES = [1, 0.85, 0.7] as const;

function closed(hadith: boolean): Candidate[] {
  const shapes: [CardShape, number][] = [
    [WIDE, SCALES[0]],
    [WIDE, SCALES[1]],
    [TALL, SCALES[0]],
    [TALL, SCALES[1]],
    [TALL, SCALES[2]],
  ];
  return shapes.map(([shape, scale]) => ({ shape, scale, hadith }));
}

/** The fixed-height cards to try, in order of preference. */
export function candidates(hasHadith: boolean): Candidate[] {
  return [...(hasHadith ? closed(true) : []), ...closed(false)];
}

/** The last resort, tried when no fixed card holds the verse: a tall card that grows to hold it. */
export const GROWING: Candidate = { shape: TALL, scale: SCALES[2], hadith: false };

export function blockSizes({ shape, scale }: Candidate) {
  return {
    verse: Math.round(shape.verseSize * scale),
    hadith: Math.round(shape.hadithSize * scale),
  };
}

export function columnWidth(shape: CardShape): number {
  return shape.width - 2 * shape.padding;
}
