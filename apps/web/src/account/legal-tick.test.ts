import { describe, expect, it, vi } from 'vitest';
import { LEGAL } from '@/test/legal';
import { rememberTick, TICK_LIFETIME_MS, takeTick, tickMatches } from './legal-tick';

const NOW = 1_800_000_000_000;

describe('the tick kept for the way back from Google', () => {
  it('is read once, while fresh, for the versions ticked', () => {
    rememberTick(LEGAL, NOW);
    const tick = takeTick(NOW + 60_000);
    expect(tick).toEqual({ terms_version: '2026-10-04', privacy_version: '2026-10-04' });
    expect(takeTick(NOW + 60_000)).toBeNull();
    expect(tickMatches(tick as NonNullable<typeof tick>, LEGAL)).toBe(true);
    expect(
      tickMatches(tick as NonNullable<typeof tick>, { ...LEGAL, privacy_version: '2027-01-01' })
    ).toBe(false);
  });

  it('is worthless after ten minutes, from the future, or garbled', () => {
    rememberTick(LEGAL, NOW);
    expect(takeTick(NOW + TICK_LIFETIME_MS + 1)).toBeNull();
    rememberTick(LEGAL, NOW);
    expect(takeTick(NOW - 1)).toBeNull();
    window.sessionStorage.setItem('tabsira.legal.tick', '{not json');
    expect(takeTick(NOW)).toBeNull();
    window.sessionStorage.setItem('tabsira.legal.tick', JSON.stringify({ at: NOW }));
    expect(takeTick(NOW)).toBeNull();
    expect(takeTick(NOW)).toBeNull();
  });

  it('does without session storage', () => {
    const blocked = vi.spyOn(window, 'sessionStorage', 'get').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => rememberTick(LEGAL)).not.toThrow();
    expect(takeTick()).toBeNull();
    blocked.mockRestore();
  });
});
