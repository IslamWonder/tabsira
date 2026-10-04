/**
 * Presentation spans over a stored hadith (DESIGN_DECISION.md «Hadith display»).
 *
 * The text is never changed: segments are slices of the stored string by
 * position, and their concatenation is the stored string, always. Offsets are
 * JavaScript string indices (UTF-16 code units), which equal Python's code-point
 * indices for Arabic text since it lies in the Basic Multilingual Plane.
 *
 * Spans the reader would see as broken are refused as a whole and the text is
 * shown in one piece instead: overlapping or unordered spans, offsets outside
 * the text, and any cut inside a word (it would break Arabic letter joining) or
 * between a letter and its diacritics.
 */

export type HadithRole = 'chain' | 'body' | 'words' | 'tail';

export interface HadithSpan {
  readonly start: number;
  readonly end: number;
  readonly role: HadithRole;
}

export interface HadithSegment {
  readonly start: number;
  readonly end: number;
  readonly role: HadithRole;
}

const ROLES: ReadonlySet<string> = new Set<HadithRole>(['chain', 'body', 'words', 'tail']);
const WORD_CHARACTER = /[\p{L}\p{M}\p{N}]/u;

function isWordCharacter(character: string): boolean {
  return WORD_CHARACTER.test(character);
}

/** A cut at `index` keeps every word, letter with its marks, and surrogate pair whole. */
export function isCleanBoundary(text: string, index: number): boolean {
  if (index <= 0 || index >= text.length) {
    return true;
  }
  const before = text.charAt(index - 1);
  const at = text.charAt(index);
  const code = at.charCodeAt(0);
  const splitsSurrogatePair = code >= 0xdc00 && code <= 0xdfff;
  return !splitsSurrogatePair && !(isWordCharacter(before) && isWordCharacter(at));
}

export function spansAreValid(text: string, spans: readonly HadithSpan[]): boolean {
  let previousEnd = 0;
  for (const span of spans) {
    const ordered =
      Number.isInteger(span.start) &&
      Number.isInteger(span.end) &&
      span.start >= previousEnd &&
      span.end >= span.start &&
      span.end <= text.length;
    if (
      !ordered ||
      !ROLES.has(span.role) ||
      !isCleanBoundary(text, span.start) ||
      !isCleanBoundary(text, span.end)
    ) {
      return false;
    }
    previousEnd = span.end;
  }
  return true;
}

/**
 * Segments covering the whole text, in order. Gaps between spans are `body`;
 * empty spans are dropped. Invalid spans yield the whole text as one `body`.
 */
export function segmentHadith(
  text: string,
  spans: readonly HadithSpan[] = []
): readonly HadithSegment[] {
  if (text === '') {
    return [];
  }
  if (!spansAreValid(text, spans)) {
    return [{ start: 0, end: text.length, role: 'body' }];
  }
  const segments: HadithSegment[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start > cursor) {
      segments.push({ start: cursor, end: span.start, role: 'body' });
    }
    if (span.end > span.start) {
      segments.push({ start: span.start, end: span.end, role: span.role });
    }
    cursor = span.end;
  }
  if (cursor < text.length) {
    segments.push({ start: cursor, end: text.length, role: 'body' });
  }
  return segments;
}
