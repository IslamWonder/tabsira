import { messages } from '@/messages';
import { COLOUR, type Parts, paint, placeFixed, placeGrowing, type Source } from './compose';
import { type CardFaces, cardFaces } from './fonts';
import {
  blockSizes,
  type Candidate,
  type CardShape,
  candidates,
  columnWidth,
  GROWING,
  type PublicInsight,
  TALL,
} from './layout';
import { drawText, type TextImage, type TextSpec } from './text-image';

const T = messages.shareCard;

type DrawText = (spec: TextSpec) => Promise<TextImage>;

/** The faces and a drawing function that remembers what it drew during one render. */
type Ctx = CardFaces & { readonly draw: DrawText };

function memoised(): DrawText {
  const drawn = new Map<string, Promise<TextImage>>();
  return (spec) => {
    const key = JSON.stringify([
      spec.text,
      spec.face.file,
      spec.weight,
      spec.size,
      spec.leading,
      spec.width,
      spec.align,
      spec.colour,
    ]);
    const known = drawn.get(key);
    if (known !== undefined) {
      return known;
    }
    const started = drawText(spec);
    drawn.set(key, started);
    return started;
  };
}

type Draw = (overrides: Partial<TextSpec> & Pick<TextSpec, 'text'>) => Promise<TextImage>;

/** The spec shared by the text of the card; each piece overrides what differs. */
function drawer(faces: Ctx, width: number): Draw {
  return (overrides) =>
    faces.draw({
      face: faces.text[0] as CardFaces['text'][number],
      size: 22,
      leading: 0.25,
      width,
      align: 'start',
      colour: COLOUR.soft,
      ...overrides,
    });
}

/** The texts that do not depend on the candidate: the header, the footer and the labels. */
async function fixedParts(insight: PublicInsight, host: string, faces: Ctx) {
  const draw = drawer(faces, 1000);
  const small = { size: 20, colour: COLOUR.muted } as const;
  const { author } = insight;
  const [brand, hostImage, label, disclosure, authorImage] = await Promise.all([
    draw({ text: messages.brand.name, size: 38, weight: 600, colour: COLOUR.emerald }),
    draw({ text: host, ...small }),
    insight.label === null ? null : draw({ text: insight.label, size: 20, colour: COLOUR.gold }),
    draw({ text: insight.disclosure, ...small, width: 640 }),
    author === null
      ? null
      : draw({
          text:
            author.public_name === null
              ? T.authorHandle(author.handle)
              : T.author(author.public_name, author.handle),
          ...small,
          width: 380,
        }),
  ]);
  return { brand, host: hostImage, label, disclosure, author: authorImage };
}

/** The label and the reference that go with a text, drawn once. */
async function labels(insight: PublicInsight, faces: Ctx) {
  const draw = drawer(faces, 600);
  const quran = insight.quran;
  const hadith = insight.hadith;
  return Promise.all([
    quran === null
      ? null
      : Promise.all([
          draw({ text: quran.tag, weight: 600, colour: COLOUR.gold }),
          draw({
            text: messages.insightPage.verseReference(quran.verse.surah_name, quran.verse.ayah),
            colour: COLOUR.muted,
          }),
        ]),
    hadith === null ? null : hadithLabels(hadith, draw),
  ]);
}

function hadithLabels(hadith: NonNullable<PublicInsight['hadith']>, draw: Draw) {
  const { collection, number } = hadith.hadith;
  return Promise.all([
    draw({ text: hadith.tag, weight: 600, colour: COLOUR.sunnah }),
    draw({
      text: messages.insightPage.hadithReference(collection.name_ar, number),
      colour: COLOUR.muted,
    }),
  ]);
}

async function titleFor(insight: PublicInsight, shape: CardShape, faces: Ctx) {
  const draw = drawer(faces, columnWidth(shape));
  let drawn = await draw({
    text: insight.title,
    size: 46,
    weight: 600,
    colour: COLOUR.gold,
    leading: 0.1,
  });
  // Two lines at most: a smaller size before a third line.
  for (const size of [40, 34]) {
    if (drawn.height <= 46 * 3.4) {
      break;
    }
    drawn = await draw({
      text: insight.title,
      size,
      weight: 600,
      colour: COLOUR.gold,
      leading: 0.1,
    });
  }
  return drawn;
}

type Pair = [TextImage, TextImage] | null;

async function sources(
  candidate: Candidate,
  insight: PublicInsight,
  faces: Ctx,
  pairs: [Pair, Pair]
): Promise<{ verse: Source | null; hadith: Source | null }> {
  const sizes = blockSizes(candidate);
  const inner = columnWidth(candidate.shape) - 2 * 24 - 5;
  const verseText = insight.quran?.verse.text;
  const hadithText = candidate.hadith ? insight.hadith?.hadith.text : undefined;
  const [verse, hadith] = await Promise.all([
    verseText === undefined || pairs[0] === null
      ? null
      : faces.draw({
          text: verseText,
          face: faces.quran,
          size: sizes.verse,
          leading: 0.2,
          width: inner,
          align: 'centre',
          colour: COLOUR.text,
        }),
    hadithText === undefined || pairs[1] === null
      ? null
      : faces.draw({
          text: hadithText,
          face: faces.text[0] as CardFaces['text'][number],
          size: sizes.hadith,
          leading: 0.45,
          width: inner,
          align: 'start',
          colour: COLOUR.text,
        }),
  ]);
  return {
    verse:
      verse === null || pairs[0] === null
        ? null
        : {
            tag: pairs[0][0],
            reference: pairs[0][1],
            text: verse,
            accent: COLOUR.gold,
            align: 'centre',
          },
    hadith:
      hadith === null || pairs[1] === null
        ? null
        : {
            tag: pairs[1][0],
            reference: pairs[1][1],
            text: hadith,
            accent: COLOUR.sunnah,
            align: 'right',
          },
  };
}

let registered: Promise<void> | undefined;

/** Registers every face with the text engine before the first real text, so a Latin letter finds its face. */
function register(faces: CardFaces): Promise<void> {
  registered ??= Promise.all(
    [...faces.text, faces.quran].map((face) =>
      drawText({
        text: 'a',
        face,
        size: 12,
        leading: 0,
        width: 100,
        align: 'start',
        colour: COLOUR.text,
      })
    )
  )
    .then(() => undefined)
    .catch((error: unknown) => {
      // A failed registration is tried again on the next card, not kept for good.
      registered = undefined;
      throw error;
    });
  return registered;
}

async function partsFor(
  candidate: Candidate,
  insight: PublicInsight,
  faces: Ctx,
  shared: { fixed: Awaited<ReturnType<typeof fixedParts>>; pairs: [Pair, Pair]; title: TextImage }
): Promise<Parts> {
  const { shape } = candidate;
  const omitted = insight.hadith !== null && !candidate.hadith;
  const draw = drawer(faces, columnWidth(shape));
  return {
    ...shared.fixed,
    title: shared.title,
    pointer: omitted ? await draw({ text: T.hadithOnPage }) : null,
    ...(await sources(candidate, insight, faces, shared.pairs)),
  };
}

type Shared = Parameters<typeof partsFor>[3];

/**
 * Whether the hadith could fit whole anywhere: alone with the title, at the
 * smallest size, on the tall card. When not, no candidate with it is worth
 * drawing, and a very long hadith is not drawn again and again to find out.
 */
async function hadithCanFit(insight: PublicInsight, faces: Ctx, shared: Shared) {
  const smallest = candidates(true).findLast((candidate) => candidate.hadith) as Candidate;
  const parts = await partsFor(smallest, insight, faces, shared);
  return placeFixed(smallest.shape, { ...parts, verse: null }) !== null;
}

/** The card as PNG bytes, with the fonts of this repository and no network. */
export async function renderCard(insight: PublicInsight, host: string): Promise<Buffer> {
  const base = cardFaces();
  await register(base);
  const faces: Ctx = { ...base, draw: memoised() };
  const fixed = await fixedParts(insight, host, faces);
  const pairs = await labels(insight, faces);
  const titles = new Map<CardShape, TextImage>();
  const titleOf = async (shape: CardShape) => {
    const title = titles.get(shape) ?? (await titleFor(insight, shape, faces));
    titles.set(shape, title);
    return title;
  };
  const sharedFor = async (shape: CardShape): Promise<Shared> => ({
    fixed,
    pairs,
    title: await titleOf(shape),
  });
  const withHadith =
    insight.hadith !== null && (await hadithCanFit(insight, faces, await sharedFor(TALL)));
  for (const candidate of candidates(withHadith)) {
    const parts = await partsFor(candidate, insight, faces, await sharedFor(candidate.shape));
    const placed = placeFixed(candidate.shape, parts);
    if (placed !== null) {
      return paint(placed);
    }
  }
  const parts = await partsFor(GROWING, insight, faces, await sharedFor(GROWING.shape));
  return paint(placeGrowing(GROWING.shape, parts));
}
