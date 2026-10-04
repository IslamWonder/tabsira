import { describe, expect, it } from 'vitest';
import {
  cleanPublicName,
  handleProblem,
  postPath,
  profilePath,
  publicNameProblem,
} from './identity';

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

describe('the public name', () => {
  it('collapses spaces and refuses links, addresses and hidden characters', () => {
    expect(cleanPublicName('  قارئ   المطر ')).toBe('قارئ المطر');
    expect(publicNameProblem('قارئ المطر')).toBeNull();
    expect(publicNameProblem('   ')).toBe('اكتب اسمًا عامًا.');
    expect(publicNameProblem('ا'.repeat(41))).toBe('الاسم العام 40 حرفًا على الأكثر.');
    expect(publicNameProblem('me@example.com')).toMatch(/بلا رابط ولا بريد/);
    expect(publicNameProblem('see https://x.y')).toMatch(/بلا رابط ولا بريد/);
    expect(publicNameProblem('www.x.y')).toMatch(/بلا رابط ولا بريد/);
    expect(publicNameProblem('a‮b')).toMatch(/بلا رابط ولا بريد/);
  });
});

describe('the public addresses', () => {
  it('percent-encode a handle and keep a post id as it is', () => {
    expect(profilePath('قارئ')).toBe('/u/%D9%82%D8%A7%D8%B1%D8%A6');
    expect(profilePath('reader')).toBe('/u/reader');
    expect(postPath('7345678901234567890')).toBe('/posts/7345678901234567890');
  });
});
