import { describe, expect, it } from 'vitest';
import { isPublicId } from './ids';

describe('isPublicId', () => {
  it('accepts the decimal ids the API writes, however large', () => {
    expect(isPublicId('1')).toBe(true);
    expect(isPublicId('110000000000000001')).toBe(true);
    expect(isPublicId('9223372036854775807')).toBe(true);
  });

  it('refuses anything else before it reaches the API', () => {
    for (const value of [
      '',
      '0',
      '01',
      '-1',
      '1.5',
      '1e3',
      'abc',
      ' 1',
      '12345678901234567890',
      '9223372036854775808',
      '9999999999999999999',
    ]) {
      expect(isPublicId(value)).toBe(false);
    }
  });
});
