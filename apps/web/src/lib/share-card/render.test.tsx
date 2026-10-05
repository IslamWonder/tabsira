// @vitest-environment node
import { createHash } from 'node:crypto';
import sharp from 'sharp';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { HADITH_TEXT, sha256, VERSE_TEXT } from '@/test/scan';
import { publicInsightOut, withLongScripture } from '@/test/share';
import { CARD_MAX_BYTES } from './compose';
import { renderCard } from './render';
import { drawText, type TextSpec } from './text-image';

vi.mock('./text-image', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./text-image')>();
  return { ...actual, drawText: vi.fn(actual.drawText) };
});

const PNG_SIGNATURE = '89504e470d0a1a0a';

async function render(insight = publicInsightOut()) {
  vi.mocked(drawText).mockClear();
  const png = await renderCard(insight, 'tabsira.test');
  const specs = vi.mocked(drawText).mock.calls.map(([spec]) => spec);
  return { png, specs, info: await sharp(png).metadata() };
}

/** The spec drawn with the Quran face: the verse, and nothing else, uses it. */
const verseSpec = (specs: TextSpec[]) =>
  specs.filter((spec) => spec.face.family.includes('KFGQPC'));

describe('the share card image', () => {
  // The first card registers the faces with the text engine; the checks below look at real cards only.
  beforeAll(() => renderCard(publicInsightOut(), 'tabsira.test'));

  it('is a PNG in the link-preview shape for a typical insight', async () => {
    const { png, info } = await render();
    expect(png.subarray(0, 8).toString('hex')).toBe(PNG_SIGNATURE);
    expect([info.width, info.height]).toEqual([1200, 630]);
  });

  it('stays under 300 KB, so messaging apps show it, from a typical card to the longest verse', async () => {
    // The fixture verse is about 30 characters; forty of them are longer than the
    // longest verse of the Quran, and twelve hadiths fill the tall card.
    const cases = [
      publicInsightOut(),
      withLongScripture(publicInsightOut(), 12, 12),
      withLongScripture(publicInsightOut(), 40, 12),
      withLongScripture(publicInsightOut(), 40, 400),
    ];
    for (const insight of cases) {
      const { png } = await render(insight);
      expect(png.length).toBeLessThan(CARD_MAX_BYTES);
    }
  });

  it('draws the verse and the hadith exactly as the API returns them, with their stored hashes', async () => {
    const insight = publicInsightOut();
    const { specs } = await render(insight);
    const [verse] = verseSpec(specs);
    const hadith = specs.find((spec) => spec.text === HADITH_TEXT);
    expect(verseSpec(specs).every((spec) => spec.text === VERSE_TEXT)).toBe(true);
    // A drawn string is the stored string, byte for byte: same text, same hash.
    expect(verse?.text).toBe(VERSE_TEXT);
    expect(sha256(verse?.text ?? '')).toBe(insight.quran?.verse.sha256);
    expect(hadith?.text).toBe(HADITH_TEXT);
    expect(sha256(hadith?.text ?? '')).toBe(insight.hadith?.hadith.sha256);
    // And no other piece of text is a changed copy of scripture.
    const others = specs
      .filter((spec) => spec.text !== VERSE_TEXT && spec.text !== HADITH_TEXT)
      .map((spec) => spec.text);
    expect(others.some((text) => text.includes(VERSE_TEXT.trim()))).toBe(false);
  });

  it('draws the hadith by its reference alone, with no ruling line', async () => {
    const insight = publicInsightOut();
    const hadith = insight.hadith;
    if (hadith === null) {
      throw new Error('the fixture has a hadith');
    }
    const { specs } = await render(insight);
    const texts = specs.map((spec) => spec.text);
    expect(texts).toContain(
      messages.insightPage.hadithReference(hadith.hadith.collection.name_ar, hadith.hadith.number)
    );
    expect(texts.some((text) => text.includes('الدرر'))).toBe(false);
  });

  it('keeps the stored hashes of a lengthened verse and hadith', () => {
    const insight = withLongScripture(publicInsightOut(), 3, 3);
    expect(sha256(insight.quran?.verse.text ?? '')).toBe(insight.quran?.verse.sha256);
    expect(sha256(insight.hadith?.hadith.text ?? '')).toBe(insight.hadith?.hadith.sha256);
  });

  it('uses the Quran face for the verse alone and Readex Pro for the rest', async () => {
    const { specs } = await render();
    expect(verseSpec(specs).length).toBeGreaterThan(0);
    expect(
      specs
        .filter((spec) => !spec.face.family.includes('KFGQPC'))
        .every((spec) => spec.face.family === 'Readex Pro')
    ).toBe(true);
  });

  it('never cuts a long verse and hadith: the tall card holds both whole', async () => {
    const insight = withLongScripture(publicInsightOut(), 12, 12);
    const { specs, info } = await render(insight);
    expect(info.height).toBe(1350);
    const texts = specs.map((spec) => spec.text);
    expect(texts).toContain(insight.quran?.verse.text);
    expect(texts).toContain(insight.hadith?.hadith.text);
    expect(sha256(texts.find((text) => text === insight.quran?.verse.text) ?? '')).toBe(
      insight.quran?.verse.sha256
    );
    expect(sha256(texts.find((text) => text === insight.hadith?.hadith.text) ?? '')).toBe(
      insight.hadith?.hadith.sha256
    );
  });

  it('leaves a hadith that cannot fit whole to the public page and says so', async () => {
    const insight = withLongScripture(publicInsightOut(), 40, 400);
    const { specs } = await render(insight);
    const texts = specs.map((spec) => spec.text);
    expect(texts).toContain(insight.quran?.verse.text);
    // The hadith was drawn to be measured, found too long, and dropped: the pointer to the page
    // is drawn only for the candidates after it, and the last hadith drawn precedes it.
    expect(texts).toContain(messages.shareCard.hadithOnPage);
    expect(texts.lastIndexOf(insight.hadith?.hadith.text ?? '')).toBeLessThan(
      texts.indexOf(messages.shareCard.hadithOnPage)
    );
  });

  it('grows the card for a verse that fits no fixed shape, rather than cutting it', async () => {
    const insight = withLongScripture(publicInsightOut(), 220, 1);
    const { specs, info } = await render(insight);
    expect(info.height ?? 0).toBeGreaterThan(1350);
    expect(specs.map((spec) => spec.text)).toContain(insight.quran?.verse.text);
  });

  it('shows the title, the label and the author as the API gives them, and no photo or place', async () => {
    const insight = publicInsightOut({
      label: 'وسم للاختبار',
      author: { handle: 'tester', public_name: 'اسم للاختبار' },
    });
    const { specs } = await render(insight);
    const texts = specs.map((spec) => spec.text);
    expect(texts).toContain(insight.title);
    expect(texts).toContain('وسم للاختبار');
    // The handle is isolated, so it keeps its own direction inside the right-to-left line.
    expect(texts).toContain(messages.shareCard.author('اسم للاختبار', 'tester'));
    expect(messages.shareCard.author('اسم للاختبار', 'tester')).toContain('\u2066@tester\u2069');
    expect(texts).toContain(messages.brand.name);
    expect(texts).toContain('tabsira.test');
    expect(texts).toContain(insight.disclosure);
  });

  it('draws a card for an insight with a verse only', async () => {
    const insight = publicInsightOut({ hadith: null, hadith_status: 'none' });
    const { specs, info } = await render(insight);
    expect([info.width, info.height]).toEqual([1200, 630]);
    expect(specs.map((spec) => spec.text)).not.toContain(messages.shareCard.hadithOnPage);
  });

  it('draws a card for an insight with a hadith only', async () => {
    const insight = publicInsightOut({ quran: null });
    const { specs } = await render(insight);
    expect(verseSpec(specs)).toHaveLength(0);
    expect(specs.map((spec) => spec.text)).toContain(HADITH_TEXT);
  });

  it('sets a long title smaller before it takes a third line', async () => {
    const insight = publicInsightOut({ title: 'عنوان طويل للبصيرة '.repeat(9) });
    const { specs } = await render(insight);
    const sizes = specs.filter((spec) => spec.text === insight.title).map((spec) => spec.size);
    expect(sizes[0]).toBe(46);
    expect(sizes.length).toBeGreaterThan(1);
  });

  it('draws each piece of text once in a card, whatever candidates were tried', async () => {
    const { specs } = await render(withLongScripture(publicInsightOut(), 40, 400));
    const keys = specs.map((spec) =>
      JSON.stringify([spec.text, spec.face.file, spec.weight, spec.size, spec.width, spec.align])
    );
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('renders a typical insight in under one second', async () => {
    await render();
    const started = performance.now();
    const { png } = await render();
    const warm = performance.now() - started;
    expect(png.length).toBeGreaterThan(0);
    expect(warm).toBeLessThan(1000);
    // The PNG itself does not depend on the clock: the same insight draws the same bytes.
    const again = await render();
    expect(createHash('sha256').update(again.png).digest('hex')).toBe(
      createHash('sha256').update(png).digest('hex')
    );
  });
});
