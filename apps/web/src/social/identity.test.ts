import { describe, expect, it } from 'vitest';
import { handleProblem, memberLabel, postPath, profilePath } from './identity';

describe('the public handle', () => {
  it('accepts Latin and Arabic handles and refuses the rest, as the API does', () => {
    expect(handleProblem(' Rain_reader ')).toBeNull();
    expect(handleProblem('قارئ_المطر٢'.replace('٢', '2'))).toBeNull();
    expect(handleProblem('')).toBe('اكتب معرّفًا.');
    expect(handleProblem('ab')).toMatch(/يبدأ بحرف/);
    expect(handleProblem('1abc')).toMatch(/يبدأ بحرف/);
    expect(handleProblem('a'.repeat(31))).toMatch(/يبدأ بحرف/);
    expect(handleProblem('has space')).toMatch(/يبدأ بحرف/);
    expect(handleProblem('مَرحبا')).toMatch(/يبدأ بحرف/);
  });

  it('refuses the names of the platform and its staff, whatever follows them', () => {
    expect(handleProblem('admin')).toBe('هذا المعرّف محجوز للمنصة.');
    expect(handleProblem('Tabsira_help')).toBe('هذا المعرّف محجوز للمنصة.');
    expect(handleProblem('مشرف_1')).toBe('هذا المعرّف محجوز للمنصة.');
    expect(handleProblem('تبصرة')).toBe('هذا المعرّف محجوز للمنصة.');
  });
});

describe('the member label', () => {
  it('is the full name when the API sent it, else the handle alone', () => {
    expect(memberLabel({ handle: 'sara_21', public_name: 'سارة' })).toBe('سارة');
    expect(memberLabel({ handle: 'sara_21', public_name: null })).toBe('@sara_21');
  });
});

describe('the public addresses', () => {
  it('percent-encode a handle and keep a post id as it is', () => {
    expect(profilePath('قارئ')).toBe('/u/%D9%82%D8%A7%D8%B1%D8%A6');
    expect(profilePath('reader')).toBe('/u/reader');
    expect(postPath('7345678901234567890')).toBe('/posts/7345678901234567890');
  });
});
