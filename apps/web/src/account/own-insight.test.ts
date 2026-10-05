import { afterEach, describe, expect, it, vi } from 'vitest';
import { USER } from '@/test/fixtures';
import { OWN_INSIGHT_KEY, rememberOwnInsight } from './own-insight';
import { forgetSession, setGuest, setSignedIn } from './session';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  forgetSession();
});

describe('the own-insight mark', () => {
  it('follows the session: set for an account with its own insight, cleared otherwise', () => {
    setSignedIn({ ...USER, has_own_insight: true });
    expect(window.localStorage.getItem(OWN_INSIGHT_KEY)).toBe('1');
    setSignedIn({ ...USER, has_own_insight: false });
    expect(window.localStorage.getItem(OWN_INSIGHT_KEY)).toBeNull();
    rememberOwnInsight(true);
    setGuest();
    expect(window.localStorage.getItem(OWN_INSIGHT_KEY)).toBeNull();
  });

  it('only loses its head start when the storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => rememberOwnInsight(true)).not.toThrow();
  });
});
