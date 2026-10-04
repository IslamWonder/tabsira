import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import {
  cleanDisplayName,
  displayNameProblem,
  emailProblem,
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
    expect(displayNameProblem('a‮b')).toBe(V.nameInvalid);
    expect(displayNameProblem('x'.repeat(61))).toBe(V.nameLong);
    expect(displayNameProblem('[اسم]')).toBeNull();
  });
});
