import { describe, expect, it } from 'vitest';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { codeMessage, failedRunMessage, journeyFailureMessage } from './failure';
import { centre, spansInUtf16 } from './spans';

function failure(code: Failure['code']): Failure {
  return { ok: false, code, status: 400, fields: [], retryAfter: null };
}

describe('the words for a failure', () => {
  it('says what to do for each code the scan and the insight can answer', () => {
    expect(codeMessage('IMAGE_TOO_LARGE')).toBe(messages.scan.errors.IMAGE_TOO_LARGE);
    expect(journeyFailureMessage(failure('IMAGE_URL_REFUSED'))).toBe(
      messages.scan.errors.IMAGE_URL_REFUSED
    );
    expect(codeMessage('NOT_A_CODE')).toBeUndefined();
  });

  it('falls back to the general words for a code with none of its own', () => {
    expect(journeyFailureMessage(failure('NETWORK'))).toBe(messages.errors.network);
    expect(journeyFailureMessage(failure('INTERNAL_ERROR'))).toBe(messages.errors.server);
  });

  it('names a failed run by its code, or as a fault of ours when it has none we know', () => {
    expect(failedRunMessage('SOURCE_UNAVAILABLE')).toBe(messages.scan.errors.SOURCE_UNAVAILABLE);
    expect(failedRunMessage('SOMETHING_NEW')).toBe(messages.errors.server);
    expect(failedRunMessage('')).toBe(messages.errors.server);
    expect(failedRunMessage(null)).toBe(messages.errors.server);
  });
});

describe('spansInUtf16', () => {
  it('leaves the offsets of a text in the Basic Multilingual Plane as they are', () => {
    const spans = [{ start: 2, end: 5, role: 'words' as const }];
    expect(spansInUtf16('مرحبا بكم', spans)).toEqual(spans);
    expect(spansInUtf16('x', [])).toEqual([]);
  });

  it('moves code-point offsets past a character outside it into UTF-16 units', () => {
    // 😀 is one code point and two UTF-16 units: «a😀b c» has code points a=0 😀=1 b=2 ' '=3 c=4.
    const text = 'a\u{1F600}b c';
    const spans = [
      { start: 0, end: 3, role: 'chain' as const },
      { start: 3, end: 5, role: 'tail' as const },
    ];
    expect(spansInUtf16(text, spans)).toEqual([
      { start: 0, end: 4, role: 'chain' },
      { start: 4, end: 6, role: 'tail' },
    ]);
  });

  it('sends an offset past the end beyond the text, where the check refuses it', () => {
    const [span] = spansInUtf16('ab', [{ start: 0, end: 9, role: 'body' }]);
    expect(span?.end).toBeGreaterThan('ab'.length);
  });
});

describe('centre', () => {
  it('is the middle of a box of ratios, which is where an insight point sits', () => {
    const point = centre({ x: 0.06, y: 0.525, width: 0.36, height: 0.06 });
    expect(point.x).toBeCloseTo(0.24, 10);
    expect(point.y).toBeCloseTo(0.555, 10);
  });
});
