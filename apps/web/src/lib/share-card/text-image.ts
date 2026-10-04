import sharp from 'sharp';
import type { Face } from './fonts';

/*
 * One piece of text, drawn by Pango (inside sharp) into a transparent picture.
 * Pango does what the page's own text engine does: it joins the letters of a
 * word, places the marks, orders mixed Arabic and Latin runs and mirrors
 * brackets. The string it is given is the one the API returned: the only change
 * is the escaping the markup needs (`&`, `<`, `>`), undone by the reader of the
 * markup, so nothing is added, removed, joined or reordered.
 */

export interface TextSpec {
  /** The text exactly as the API returns it. */
  readonly text: string;
  readonly face: Face;
  readonly weight?: 400 | 600;
  /** Pixels. */
  readonly size: number;
  /** Extra space between lines, as a multiple of the size, over the face's own line height. */
  readonly leading: number;
  /** The width the lines wrap at. */
  readonly width: number;
  readonly align: 'right' | 'centre';
  readonly colour: string;
}

export interface TextImage {
  readonly png: Buffer;
  readonly width: number;
  readonly height: number;
}

const ESCAPES: Readonly<Record<string, string>> = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };
const UNESCAPES: Readonly<Record<string, string>> = { '&amp;': '&', '&lt;': '<', '&gt;': '>' };

/** What markup needs to carry any text: three characters written as entities. */
export function escapeMarkup(text: string): string {
  return text.replace(/[&<>]/g, (character) => ESCAPES[character] as string);
}

/** The inverse of `escapeMarkup`, for the checks that the text survives the trip. */
export function unescapeMarkup(markup: string): string {
  return markup.replace(/&(?:amp|lt|gt);/g, (entity) => UNESCAPES[entity] as string);
}

export function markup({ text, colour, weight = 400 }: TextSpec): string {
  return `<span foreground="${colour}" weight="${weight}">${escapeMarkup(text)}</span>`;
}

/** Draws the text; the height is the layout's own, never a guess. */
export async function drawText(spec: TextSpec): Promise<TextImage> {
  const { data, info } = await sharp({
    text: {
      text: markup(spec),
      font: `${spec.face.family} ${spec.size}px`,
      fontfile: spec.face.file,
      width: spec.width,
      align: spec.align,
      rgba: true,
      wrap: 'word',
      spacing: Math.round(spec.size * spec.leading),
      dpi: 72,
    },
  })
    .png()
    .toBuffer({ resolveWithObject: true });
  return { png: data, width: info.width, height: info.height };
}
