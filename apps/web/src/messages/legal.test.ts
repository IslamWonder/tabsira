import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { legal, legalMessages, PRIVACY_VERSION, TERMS_VERSION } from './legal';

const ENV_EXAMPLE = path.resolve(__dirname, '../../../../.env.example');

function envExampleValue(key: string): string | undefined {
  const line = readFileSync(ENV_EXAMPLE, 'utf8')
    .split('\n')
    .find((candidate) => candidate.startsWith(`${key}=`));
  return line?.slice(key.length + 1).trim();
}

const { terms, privacy, support } = legal.ar;

function everyText(document: typeof terms): string[] {
  return [
    document.title,
    document.description,
    document.intro,
    ...document.sections.flatMap((section) => [
      section.heading,
      ...section.blocks.flatMap((block) => (block.kind === 'p' ? [block.text] : block.items)),
    ]),
  ];
}

describe('legal versions', () => {
  it('are times (decision 64: the profile, the full name and the guest limit; task 16.3: views), each on the day its printed date names', () => {
    expect(TERMS_VERSION).toBe('2026-10-05T18:00Z');
    expect(PRIVACY_VERSION).toBe('2026-10-06T17:00Z');
    // A valid global date-and-time string: it is the <time> element's dateTime and the page's dateModified.
    expect(TERMS_VERSION).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/);
    expect(terms.updated).toBe('5 أكتوبر 2026');
    expect(privacy.updated).toBe('6 أكتوبر 2026');
  });

  // The keys land in .env.example with the API branch; until then the defaults held here are the reference.
  it('equal TERMS_VERSION and PRIVACY_VERSION in .env.example once they exist', () => {
    expect(envExampleValue('TERMS_VERSION') ?? TERMS_VERSION).toBe(TERMS_VERSION);
    expect(envExampleValue('PRIVACY_VERSION') ?? PRIVACY_VERSION).toBe(PRIVACY_VERSION);
  });
});

describe('legal documents', () => {
  it.each([
    ['terms', terms],
    ['privacy', privacy],
  ])(
    '%s: ASCII unique anchors, headings, no empty text, search-result lengths',
    (_name, document) => {
      const ids = document.sections.map((section) => section.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const id of ids) {
        expect(id).toMatch(/^[a-z][a-z-]*$/);
      }
      for (const text of everyText(document)) {
        expect(text.trim()).not.toBe('');
      }
      expect(document.title.length).toBeLessThanOrEqual(65);
      expect(document.description.length).toBeLessThanOrEqual(165);
    }
  );

  it('use no dash and no markdown in visible copy, and keep to one sentence form of quotes', () => {
    const all = [...everyText(terms), ...everyText(privacy)].join('\n');
    expect(all).not.toMatch(/[–—]/);
    expect(all).not.toMatch(/(\*\*|\n#|\]\()/);
    expect(all).not.toContain('.test');
  });

  it('terms cover what the owners asked for', () => {
    const ids = terms.sections.map((section) => section.id);
    for (const id of [
      'what-is',
      'not-a-ruling',
      'scripture',
      'accounts',
      'your-content',
      'acceptable-use',
      'reports-moderation',
      'photos-location',
      'termination',
      'changes',
      'contact',
    ]) {
      expect(ids).toContain(id);
    }
    const text = everyText(terms).join('\n');
    // The support address is never shown: the support form is the way in.
    expect(text).not.toContain('support@');
    expect(text).toContain('https://tabsira.me/support');
    expect(text).toContain('privacy@tabsira.me');
    expect(text).toContain('فتوى');
  });

  it('privacy names every data flow of docs/PRIVACY.md and of the decisions', () => {
    const text = everyText(privacy).join('\n');
    for (const needle of [
      'privacy@tabsira.me',
      'OpenAI',
      'OVHcloud',
      'EXIF',
      'GlitchTip',
      'Google Analytics',
      'Clarity',
      'OpenFreeMap',
      'S3',
      'nginx',
      'خمس دقائق',
      'SMTP',
      'GeoNames',
      'bcrypt',
      'SHA-256',
      '13',
      '30 يومًا',
      'لم تُحدد بعد',
    ]) {
      expect(text).toContain(needle);
    }
    expect(privacy.sections.map((section) => section.id)).toEqual(
      expect.arrayContaining(['rights', 'retention', 'children', 'cookies', 'location', 'support'])
    );
  });

  it('names no governing law and no company', () => {
    const text = [...everyText(terms), ...everyText(privacy)].join('\n');
    expect(text).not.toMatch(/القانون (الواجب|الحاكم)|تختص المحاكم|شركة/);
  });
});

describe('support messages', () => {
  it('keeps the description short and points data requests to privacy@tabsira.me', () => {
    expect(support.description.length).toBeLessThanOrEqual(165);
    expect(support.privacyEmail).toBe('privacy@tabsira.me');
  });

  it('builds its counters and limits', () => {
    expect(support.form.count(7)).toBe('7 من 4000');
    expect(support.errors.messageShort(20)).toContain('20');
    expect(support.errors.messageLong(4000)).toContain('4000');
  });

  it('offers exactly the six topics of the API', () => {
    expect(Object.keys(support.topics)).toEqual([
      'account',
      'privacy',
      'bug',
      'content',
      'suggestion',
      'other',
    ]);
  });

  it('is served by language, Arabic by default', () => {
    expect(legalMessages()).toBe(legal.ar);
    expect(legalMessages('ar')).toBe(legal.ar);
  });
});
