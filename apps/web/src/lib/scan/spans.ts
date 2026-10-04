import type { HadithSpan } from '@/components/insight/hadith-segments';

export interface ApiSpan {
  readonly start: number;
  readonly end: number;
  readonly role: HadithSpan['role'];
}

/**
 * The API counts a hadith's display spans in Unicode code points; the page
 * slices the text in UTF-16 units. They are the same for Arabic in the Basic
 * Multilingual Plane, and differ after any character outside it, so the
 * offsets are converted. Only the offsets change, never the text.
 */
export function spansInUtf16(text: string, spans: readonly ApiSpan[]): HadithSpan[] {
  if (spans.length === 0) {
    return [];
  }
  const offsets: number[] = [];
  let index = 0;
  for (const character of text) {
    offsets.push(index);
    index += character.length;
  }
  offsets.push(index);
  // An offset past the end maps beyond the text, where the span check refuses it.
  const at = (codePoint: number) => offsets[codePoint] ?? text.length + 1;
  return spans.map((span) => ({ start: at(span.start), end: at(span.end), role: span.role }));
}

/** A box of 0–1 ratios as the point at its centre, which is where an insight's point sits. */
export function centre(box: { x: number; y: number; width: number; height: number }): {
  x: number;
  y: number;
} {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
