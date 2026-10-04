import { describe, expect, it, vi } from 'vitest';
import { CONSENT_COOKIE, clearConsentId, readConsentId, writeConsentId } from './cookie';

describe('the consent cookie', () => {
  it('keeps the consent id, and only an id', () => {
    expect(readConsentId()).toBeNull();
    writeConsentId('c0ffee00-1234');
    expect(document.cookie).toContain(`${CONSENT_COOKIE}=c0ffee00-1234`);
    expect(readConsentId()).toBe('c0ffee00-1234');
    clearConsentId();
    expect(readConsentId()).toBeNull();
  });

  it('ignores other cookies and a value that is not an id', () => {
    expect(readConsentId('a=1; tabsira_consent=%3Cscript%3E')).toBeNull();
    expect(readConsentId('a=1;  tabsira_consent=abcdefgh')).toBe('abcdefgh');
  });
});

describe('the consent cookie over https', () => {
  it('is Secure and Lax, and outlives one choice so a lapsed one is known', () => {
    vi.stubGlobal('location', { ...window.location, protocol: 'https:' });
    const set = vi.spyOn(document, 'cookie', 'set');
    writeConsentId('c0ffee00-1234');
    expect(set).toHaveBeenCalledWith(
      'tabsira_consent=c0ffee00-1234; Path=/; Max-Age=34128000; SameSite=Lax; Secure'
    );
  });
});
