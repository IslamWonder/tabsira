import { describe, expect, it } from 'vitest';
import { hadithGradeLine } from './hadith-grade';

describe('hadithGradeLine', () => {
  it('names the first grader and their grade in Arabic', () => {
    expect(
      hadithGradeLine([
        { name: 'Al-Albani', grade: 'Hasan Sahih' },
        { name: 'Zubair Ali Zai', grade: 'Daif' },
      ])
    ).toBe('حكم الألباني: حسن صحيح');
  });

  it('skips a grade it cannot write in Arabic and takes the next one', () => {
    expect(
      hadithGradeLine([
        { name: 'Al-Albani', grade: 'Sahih Muslim' },
        { name: 'Unknown', grade: 'Sahih' },
        { name: 'Abu Ghuddah', grade: 'Daif Isnaad' },
      ])
    ).toBe('حكم أبي غدة: ضعيف الإسناد');
  });

  it('shows nothing when the dataset has no usable grade', () => {
    expect(hadithGradeLine(null)).toBeNull();
    expect(hadithGradeLine(undefined)).toBeNull();
    expect(hadithGradeLine([])).toBeNull();
    expect(hadithGradeLine([{ name: 'Al-Albani', grade: '-' }])).toBeNull();
  });
});
