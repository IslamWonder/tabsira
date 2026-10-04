import { describe, expect, it } from 'vitest';
import { cx } from './cx';
import { apiOrigin, profileQuestionsMax, siteOrigin } from './site';

describe('site addresses', () => {
  it('fall back to the development hosts when nothing was inlined', () => {
    expect(siteOrigin().href).toBe('https://tabsira.test/');
    expect(apiOrigin()).toBe('https://api.tabsira.test');
  });

  it('use the values next.config.ts inlined', () => {
    expect(siteOrigin('https://tabsira.me').href).toBe('https://tabsira.me/');
    expect(apiOrigin('https://api.tabsira.me')).toBe('https://api.tabsira.me');
  });
});

describe('profileQuestionsMax', () => {
  it('asks three by default and what the build inlined otherwise', () => {
    expect(profileQuestionsMax()).toBe(3);
    expect(profileQuestionsMax('1')).toBe(1);
  });
});

describe('cx', () => {
  it('joins the truthy class names', () => {
    expect(cx('a', false, null, undefined, '', 'b')).toBe('a b');
  });
});
