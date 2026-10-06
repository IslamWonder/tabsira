import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import {
  cleanDisplayName,
  displayNameProblem,
  emailProblem,
  hasEmailShape,
  newPasswordProblem,
  passwordMissing,
} from './validation';

const V = messages.auth.validation;

describe('the account field rules', () => {
  it('wants an address that looks like one', () => {
    expect(emailProblem('  ')).toBe(V.emailMissing);
    expect(emailProblem('name@')).toBe(V.emailInvalid);
    expect(emailProblem(' name@example.com ')).toBeNull();
  });

  it('only asks a signing-in password to be there', () => {
    expect(passwordMissing('')).toBe(V.passwordMissing);
    expect(passwordMissing('x')).toBeNull();
  });

  it('holds a new password to ten characters and 72 bytes', () => {
    expect(newPasswordProblem('')).toBe(V.passwordMissing);
    expect(newPasswordProblem('short')).toBe(V.passwordShort);
    expect(newPasswordProblem('a'.repeat(10))).toBeNull();
    // Arabic letters take two bytes each: 40 of them are 80 bytes.
    expect(newPasswordProblem('ب'.repeat(40))).toBe(V.passwordLong);
  });

  it('cleans a name as the API does and refuses hidden characters', () => {
    expect(cleanDisplayName('  [اسم]   [آخر] ')).toBe('[اسم] [آخر]');
    expect(displayNameProblem('   ')).toBe(V.nameMissing);
    expect(displayNameProblem('a\u202Eb')).toBe(V.nameInvalid);
    expect(displayNameProblem('x'.repeat(61))).toBe(V.nameLong);
    expect(displayNameProblem('[اسم]')).toBeNull();
  });
});

describe('hasEmailShape', () => {
  const REFERENCE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const PIECES = ['a', '.', '@', ' ', 'ب', '\n', 'ab'];

  function* words(length: number): Generator<string> {
    if (length === 0) {
      yield '';
      return;
    }
    for (const rest of words(length - 1)) {
      for (const piece of PIECES) {
        yield piece + rest;
      }
    }
  }

  it('accepts and refuses what the single pattern did', () => {
    const differing: string[] = [];
    for (let length = 0; length <= 6; length += 1) {
      for (const word of words(length)) {
        if (hasEmailShape(word) !== REFERENCE.test(word)) {
          differing.push(word);
        }
      }
    }
    expect(differing).toEqual([]);
    for (const word of [
      'a@b.c',
      'a@.b',
      'a@b.',
      'a@b..c',
      '@b.c',
      'a@@b.c',
      'a@b.c@d',
      'a b@c.d',
    ]) {
      expect(hasEmailShape(word), word).toBe(REFERENCE.test(word));
    }
  });

  it('answers at once for a long run of dots', () => {
    const started = performance.now();
    expect(hasEmailShape(`a@${'.'.repeat(50_000)} `)).toBe(false);
    expect(hasEmailShape(`a@${'.'.repeat(50_000)}`)).toBe(true);
    expect(performance.now() - started).toBeLessThan(500);
  });
});
