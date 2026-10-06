/**
 * The reading aids (text size, contrast, links): their keys, attributes and values.
 *
 * No 'use client' here: the head script (init-script.ts) is built on the server, where the exports
 * of a client module are references, not values. The hooks live in accessibility.ts.
 */

export const TEXT_SIZES = ['normal', 'large', 'larger'] as const;
export type TextSize = (typeof TEXT_SIZES)[number];

export interface ReadingAid<T extends string> {
  /** The localStorage key. */
  key: string;
  /** The data attribute on <html>, without its `data-` prefix; absent at the default. */
  attribute: string;
  values: readonly T[];
  fallback: T;
}

export const TEXT_SIZE: ReadingAid<TextSize> = {
  key: 'tabsira.text-size',
  attribute: 'text-size',
  values: TEXT_SIZES,
  fallback: 'normal',
};

export const CONTRAST: ReadingAid<'normal' | 'more'> = {
  key: 'tabsira.contrast',
  attribute: 'contrast',
  values: ['normal', 'more'],
  fallback: 'normal',
};

export const LINKS: ReadingAid<'normal' | 'underline'> = {
  key: 'tabsira.links',
  attribute: 'links',
  values: ['normal', 'underline'],
  fallback: 'normal',
};

/** Every reading aid, for the script that applies them before the first paint. */
export const READING_AIDS = [TEXT_SIZE, CONTRAST, LINKS] as const;
