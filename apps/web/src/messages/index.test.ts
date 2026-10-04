import { describe, expect, it } from 'vitest';
import { ar } from './ar';
import { getMessages, LANGUAGES, messages, SITE_LANGUAGE, siteLanguage } from './index';

describe('the languages (owner decision 36)', () => {
  it('serves Arabic, right to left, from one setting', () => {
    expect(Object.keys(LANGUAGES)).toEqual(['ar']);
    expect(SITE_LANGUAGE).toBe('ar');
    expect(siteLanguage).toEqual({
      tag: 'ar',
      dir: 'rtl',
      ogLocale: 'ar_AR',
      intl: 'ar-u-nu-latn',
    });
    expect(getMessages('ar')).toBe(ar);
    expect(getMessages()).toBe(messages);
  });
});
