import { describe, expect, it } from 'vitest';
import {
  type HadithRole,
  type HadithSpan,
  isCleanBoundary,
  segmentHadith,
  spansAreValid,
} from './hadith-segments';

// Placeholder pieces only; no hadith is typed into a test.
const CHAIN = '[سند الحديث]، ';
const BODY = '[متن الحديث] ';
const WORDS = '[الكلمات]';
const TAIL = ' [تعليق]';
const TEXT = CHAIN + BODY + WORDS + TAIL;

function spansFor(parts: ReadonlyArray<readonly [HadithRole, string]>): HadithSpan[] {
  let start = 0;
  return parts.map(([role, part]) => {
    const span = { start, end: start + part.length, role };
    start += part.length;
    return span;
  });
}

function joined(text: string, spans: readonly HadithSpan[]) {
  return segmentHadith(text, spans)
    .map((segment) => text.slice(segment.start, segment.end))
    .join('');
}

describe('segmentHadith', () => {
  it('cuts the stored text into the given roles', () => {
    const spans = spansFor([
      ['chain', CHAIN],
      ['body', BODY],
      ['words', WORDS],
      ['tail', TAIL],
    ]);
    const segments = segmentHadith(TEXT, spans);
    expect(segments.map((segment) => segment.role)).toEqual(['chain', 'body', 'words', 'tail']);
    expect(joined(TEXT, spans)).toBe(TEXT);
  });

  it('fills the gaps between spans as body and drops empty spans', () => {
    const wordsStart = CHAIN.length + BODY.length;
    const spans: HadithSpan[] = [
      { start: 0, end: 0, role: 'chain' },
      { start: wordsStart, end: wordsStart + WORDS.length, role: 'words' },
    ];
    expect(segmentHadith(TEXT, spans)).toEqual([
      { start: 0, end: wordsStart, role: 'body' },
      { start: wordsStart, end: wordsStart + WORDS.length, role: 'words' },
      { start: wordsStart + WORDS.length, end: TEXT.length, role: 'body' },
    ]);
  });

  it('returns the whole text as body without spans, and nothing for an empty text', () => {
    expect(segmentHadith(TEXT)).toEqual([{ start: 0, end: TEXT.length, role: 'body' }]);
    expect(segmentHadith('', [])).toEqual([]);
  });

  it.each([
    [
      'overlapping',
      [
        { start: 0, end: 10, role: 'chain' },
        { start: 5, end: 12, role: 'body' },
      ],
    ],
    ['reversed', [{ start: 10, end: 5, role: 'chain' }]],
    ['past the end', [{ start: 0, end: TEXT.length + 1, role: 'chain' }]],
    ['negative', [{ start: -1, end: 3, role: 'chain' }]],
    ['fractional', [{ start: 0.5, end: 3, role: 'chain' }]],
    ['unknown role', [{ start: 0, end: CHAIN.length, role: 'preface' }]],
    ['inside a word', [{ start: 0, end: 3, role: 'chain' }]],
  ])('shows the text whole when the spans are %s', (_name, spans) => {
    const given = spans as unknown as HadithSpan[];
    expect(spansAreValid(TEXT, given)).toBe(false);
    expect(segmentHadith(TEXT, given)).toEqual([{ start: 0, end: TEXT.length, role: 'body' }]);
  });

  it('never loses or adds a character, whatever the spans', () => {
    // Deterministic pseudo-random spans over a text with marks and joiners.
    const text = `${TEXT}\u064E\u0651 \u200F"\u200F ${WORDS}`;
    let seed = 7;
    const next = (limit: number) => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % limit;
    };
    const roles: HadithRole[] = ['chain', 'body', 'words', 'tail'];
    for (let round = 0; round < 500; round += 1) {
      const cuts = Array.from({ length: next(6) }, () => next(text.length + 1)).sort(
        (a, b) => a - b
      );
      const spans: HadithSpan[] = [];
      for (let i = 0; i + 1 < cuts.length; i += 2) {
        spans.push({
          start: cuts[i] as number,
          end: cuts[i + 1] as number,
          role: roles[next(4)] as HadithRole,
        });
      }
      expect(joined(text, spans)).toBe(text);
    }
  });
});

describe('isCleanBoundary', () => {
  it('accepts both ends of the text and cuts next to spaces or punctuation', () => {
    expect(isCleanBoundary(TEXT, 0)).toBe(true);
    expect(isCleanBoundary(TEXT, TEXT.length)).toBe(true);
    expect(isCleanBoundary(TEXT, CHAIN.length)).toBe(true);
  });

  it('refuses a cut between two letters, or between a letter and its mark', () => {
    expect(isCleanBoundary('ابت', 1)).toBe(false);
    expect(isCleanBoundary('بَ', 1)).toBe(false);
  });

  it('refuses a cut through a surrogate pair', () => {
    expect(isCleanBoundary('a\u{1F327}b', 2)).toBe(false);
  });
});
