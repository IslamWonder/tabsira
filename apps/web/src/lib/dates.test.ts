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
  it('decides the day in the zone it is given, not the server zone', () => {
    const late = '2026-10-04T23:30:00Z';
    expect(formatDay(late, 'UTC')).toMatch(/\b4\b/);
    expect(formatDay(late, 'Pacific/Kiritimati')).toMatch(/\b5\b/);
  });

  it('writes a day without the time of day', () => {
    const text = formatDay('2026-10-04T09:30:00Z');
    expect(text).toMatch(/2026/);
    expect(text).not.toMatch(/[٠-٩]|:/);
  });
});
