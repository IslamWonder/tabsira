import { messages } from '@/messages';

/*
 * The same rules the API applies (apps/api/src/schemas/auth.py and
 * src/security.py), checked before sending so a reader learns of a mistake at
 * the field, at once (tajriba §3.5, Doherty threshold). The API stays the
 * judge: its answer is shown as well when it refuses.
 */

const V = messages.auth.validation;

export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_BYTES = 72;
export const DISPLAY_NAME_MAX = 60;

// Control, format, surrogate and private-use characters (newlines, bidi tricks).
const FORBIDDEN_IN_NAME = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}]/u;

/**
 * A local part, one `@`, and a domain with a dot that has a character on each side; no
 * whitespace anywhere. Written as steps because the single pattern backtracks in quadratic
 * time on a long run of dots.
 */
export function hasEmailShape(value: string): boolean {
  const at = value.indexOf('@');
  if (at < 1 || value.includes('@', at + 1) || /\s/.test(value)) {
    return false;
  }
  const domain = value.slice(at + 1);
  const dot = domain.indexOf('.', 1);
  return dot !== -1 && dot <= domain.length - 2;
}

export function emailProblem(value: string): string | null {
  const email = value.trim();
  if (email === '') {
    return V.emailMissing;
  }
  return hasEmailShape(email) ? null : V.emailInvalid;
}

/** For signing in, only presence: a wrong password is wrong, not badly formed. */
export function passwordMissing(value: string): string | null {
  return value === '' ? V.passwordMissing : null;
}

/** For choosing a password: at least ten characters, at most 72 bytes once encoded. */
export function newPasswordProblem(value: string): string | null {
  if (value === '') {
    return V.passwordMissing;
  }
  if (value.length < PASSWORD_MIN_LENGTH) {
    return V.passwordShort;
  }
  return new TextEncoder().encode(value).length > PASSWORD_MAX_BYTES ? V.passwordLong : null;
}

/** The name as the API stores it: spaces collapsed, at most 60 characters, no hidden characters. */
export function cleanDisplayName(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(' ');
}

export function displayNameProblem(value: string): string | null {
  const name = cleanDisplayName(value);
  if (name === '') {
    return V.nameMissing;
  }
  if (FORBIDDEN_IN_NAME.test(name)) {
    return V.nameInvalid;
  }
  return name.length > DISPLAY_NAME_MAX ? V.nameLong : null;
}
