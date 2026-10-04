import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { setGuest, setSignedIn } from '@/account/session';
import { USER } from '@/test/fixtures';
import { AccountPreferencesSync } from './account-preferences-sync';

const syncFromAccount = vi.hoisted(() => vi.fn(async () => undefined));
vi.mock('@/preferences/account-sync', () => ({ syncFromAccount }));

describe('AccountPreferencesSync', () => {
  it('lets the account win once signed in, and asks nothing for a guest', () => {
    setGuest();
    const { container, rerender } = render(<AccountPreferencesSync />);
    expect(container).toBeEmptyDOMElement();
    expect(syncFromAccount).not.toHaveBeenCalled();
    setSignedIn(USER);
    rerender(<AccountPreferencesSync />);
    expect(syncFromAccount).toHaveBeenCalledTimes(1);
  });
});
