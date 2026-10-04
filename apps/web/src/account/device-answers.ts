import type { ProfilePatch } from './profile';

/**
 * A guest has no profile on the server, so the optional questions asked after
 * the first insight (master prompt v2 §5) keep their answers on the device,
 * with the fact that they were asked, so a returning guest is never asked
 * again (§4.9). The first sign-in moves them into the account and clears the
 * device (preferences/account-sync). Only the three question fields are kept.
 */

export const ANSWERS_STORAGE_KEY = 'tabsira.profile-answers';

export type QuestionAnswers = Pick<ProfilePatch, 'goals' | 'knowledge_level' | 'age_range'>;

interface Stored {
  asked: true;
  answers: QuestionAnswers;
}

function read(): Stored | null {
  try {
    const raw = window.localStorage.getItem(ANSWERS_STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || !('answers' in parsed)) {
      return null;
    }
    return { asked: true, answers: (parsed as Stored).answers ?? {} };
  } catch {
    return null;
  }
}

function write(stored: Stored): void {
  try {
    window.localStorage.setItem(ANSWERS_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Private mode or a full store: the questions are offered again next time.
  }
}

/** Whether this device's guest was already offered the questions. */
export function deviceQuestionsAsked(): boolean {
  return read() !== null;
}

/** Keeps one answer on the device; marks the questions asked. */
export function rememberDeviceAnswer(answer: QuestionAnswers): void {
  const current = read()?.answers ?? {};
  write({ asked: true, answers: { ...current, ...answer } });
}

/** Marks the questions asked, keeping whatever was answered so far. */
export function markDeviceQuestionsAsked(): void {
  write({ asked: true, answers: read()?.answers ?? {} });
}

/** The answers a guest gave on this device, or null when they were never asked. */
export function readDeviceAnswers(): QuestionAnswers | null {
  return read()?.answers ?? null;
}

export function clearDeviceAnswers(): void {
  try {
    window.localStorage.removeItem(ANSWERS_STORAGE_KEY);
  } catch {
    // Nothing to clear when the store is unreachable.
  }
}
