import { describe, expect, it } from 'vitest';
import { formatDay, formatWhen } from './dates';

describe('formatWhen', () => {
  it('writes a date in Arabic words with Western digits', () => {
    const text = formatWhen('2026-10-04T09:30:00Z');
    expect(text).toMatch(/2026/);
    expect(text).toMatch(/أكتوبر|تشرين/);
    expect(text).not.toMatch(/[٠-٩]/);
  });
});

describe('formatDay', () => {
  it('writes a day without the time of day', () => {
    const text = formatDay('2026-10-04T09:30:00Z');
    expect(text).toMatch(/2026/);
    expect(text).not.toMatch(/[٠-٩]|:/);
  });
});
