import sharp from 'sharp';
import type { CardShape } from './layout';
import type { TextImage } from './text-image';

/*
 * Places measured pieces on the card. Everything here is arithmetic on sizes
 * that were measured, so what is placed is exactly what fits; and the card is
 * right to left: it starts at the right edge.
 */

export const COLOUR = {
  ground: '#0B1210',
  groundLift: '#10201B',
  text: '#EEF3EF',
  soft: '#C3D4CC',
  muted: '#93A79E',
  gold: '#E6C77F',
  emerald: '#3FD69A',
  sunnah: '#8FEAC2',
} as const;

export const GAP = 18;
export const PANEL_PADDING = 24;
export const PANEL_EDGE = 5;
const PANEL_TOP = 12;
const PANEL_BOTTOM = 18;
const PANEL_INNER_GAP = 8;
const REFERENCE_GAP = 14;
const PILL_X = 16;
const PILL_Y = 5;
const PILL_GAP = 18;

/** A piece of scripture with its label and reference, each measured. */
export interface Source {
  readonly tag: TextImage;
  readonly reference: TextImage;
  readonly text: TextImage;
  readonly accent: string;
  readonly align: 'right' | 'centre';
}

export interface Parts {
  readonly brand: TextImage;
  readonly host: TextImage;
  readonly label: TextImage | null;
  readonly disclosure: TextImage;
  readonly author: TextImage | null;
  readonly title: TextImage;
  readonly pointer: TextImage | null;
  readonly verse: Source | null;
  readonly hadith: Source | null;
}

export interface Layer {
  readonly input: Buffer;
  readonly left: number;
  readonly top: number;
}

export interface Placed {
  readonly width: number;
  readonly height: number;
  readonly layers: Layer[];
}

interface Spot {
  /** Right edge of the card's column, where Arabic starts. */
  right: number;
  left: number;
}

function svg(width: number, height: number, body: string): Buffer {
  const open = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">`;
  return Buffer.from(`${open}${body}</svg>`);
}

function background(width: number, height: number): Buffer {
  return svg(
    width,
    height,
    `<defs><linearGradient id="g" x1="0.3" y1="0" x2="0.7" y2="1">` +
      `<stop offset="0" stop-color="${COLOUR.groundLift}"/>` +
      `<stop offset="0.6" stop-color="${COLOUR.ground}"/></linearGradient></defs>` +
      `<rect width="${width}" height="${height}" fill="url(#g)"/>`
  );
}

function pill(label: TextImage): { input: Buffer; width: number; height: number } {
  const width = label.width + 2 * PILL_X;
  const height = label.height + 2 * PILL_Y;
  const body =
    `<rect x="1" y="1" width="${width - 2}" height="${height - 2}" rx="${(height - 2) / 2}" ` +
    `fill="none" stroke="${COLOUR.gold}" stroke-width="1.5"/>`;
  return { input: svg(width, height, body), width, height };
}

function header(parts: Parts, spot: Spot, top: number): { height: number; layers: Layer[] } {
  const { brand, host, label } = parts;
  const pilled = label === null ? null : pill(label);
  const height = Math.max(brand.height, host.height, pilled?.height ?? 0);
  const middle = (item: number) => top + (height - item) / 2;
  const layers: Layer[] = [
    { input: brand.png, left: spot.right - brand.width, top: middle(brand.height) },
    { input: host.png, left: spot.left, top: middle(host.height) },
  ];
  if (pilled !== null && label !== null) {
    const left = spot.left + host.width + PILL_GAP;
    layers.push(
      { input: pilled.input, left, top: middle(pilled.height) },
      { input: label.png, left: left + PILL_X, top: middle(label.height) }
    );
  }
  return { height, layers };
}

function footerHeight({ disclosure, author }: Parts): number {
  return Math.max(disclosure.height, author?.height ?? 0);
}

function footer(parts: Parts, spot: Spot, bottom: number): Layer[] {
  const { disclosure, author } = parts;
  const height = footerHeight(parts);
  const middle = (item: number) => bottom - height + (height - item) / 2;
  const layers: Layer[] = [
    { input: disclosure.png, left: spot.right - disclosure.width, top: middle(disclosure.height) },
  ];
  if (author !== null) {
    layers.push({ input: author.png, left: spot.left, top: middle(author.height) });
  }
  return layers;
}

export function panelHeight(source: Source): number {
  const reference = Math.max(source.tag.height, source.reference.height);
  return PANEL_TOP + reference + PANEL_INNER_GAP + source.text.height + PANEL_BOTTOM;
}

function panel(source: Source, spot: Spot, top: number): Layer[] {
  const width = spot.right - spot.left;
  const height = panelHeight(source);
  const reference = Math.max(source.tag.height, source.reference.height);
  const innerRight = spot.right - PANEL_EDGE - PANEL_PADDING;
  const innerLeft = spot.left + PANEL_PADDING;
  const tagLeft = innerRight - source.tag.width;
  const textTop = top + PANEL_TOP + reference + PANEL_INNER_GAP;
  const textLeft =
    source.align === 'centre'
      ? innerLeft + (innerRight - innerLeft - source.text.width) / 2
      : innerRight - source.text.width;
  const body =
    `<rect width="${width}" height="${height}" rx="20" fill="${source.accent}" fill-opacity="0.09"/>` +
    `<rect x="${width - PANEL_EDGE}" y="14" width="${PANEL_EDGE}" height="${height - 28}" ` +
    `rx="${PANEL_EDGE / 2}" fill="${source.accent}"/>`;
  return [
    { input: svg(width, height, body), left: spot.left, top },
    {
      input: source.tag.png,
      left: tagLeft,
      top: top + PANEL_TOP + (reference - source.tag.height) / 2,
    },
    {
      input: source.reference.png,
      left: tagLeft - REFERENCE_GAP - source.reference.width,
      top: top + PANEL_TOP + (reference - source.reference.height) / 2,
    },
    { input: source.text.png, left: textLeft, top: textTop },
  ];
}

interface Block {
  height: number;
  place: (top: number) => Layer[];
}

function content(parts: Parts, spot: Spot): Block[] {
  const line = (image: TextImage): Block => ({
    height: image.height,
    place: (top) => [{ input: image.png, left: spot.right - image.width, top }],
  });
  const source = (item: Source): Block => ({
    height: panelHeight(item),
    place: (top) => panel(item, spot, top),
  });
  return [
    line(parts.title),
    ...(parts.verse === null ? [] : [source(parts.verse)]),
    ...(parts.hadith === null ? [] : [source(parts.hadith)]),
    ...(parts.pointer === null ? [] : [line(parts.pointer)]),
  ];
}

interface Stack {
  /** Everything but the texts: margins, header, footer and the gaps around the content. */
  frame: number;
  wanted: number;
  layers: (height: number) => Layer[];
}

function stack(shape: CardShape, parts: Parts): Stack {
  const spot: Spot = { right: shape.width - shape.padding, left: shape.padding };
  const head = header(parts, spot, shape.padding);
  const blocks = content(parts, spot);
  const wanted =
    blocks.reduce((total, block) => total + block.height, 0) + GAP * (blocks.length - 1);
  const frame = 2 * shape.padding + head.height + footerHeight(parts) + 2 * GAP;
  return {
    frame,
    wanted,
    layers: (height) => {
      // The footer sits at the bottom of the card, which has grown when it grows.
      const layers: Layer[] = [...head.layers, ...footer(parts, spot, height - shape.padding)];
      let top = shape.padding + head.height + GAP + (height - frame - wanted) / 2;
      for (const block of blocks) {
        layers.push(...block.place(top));
        top += block.height + GAP;
      }
      return layers;
    },
  };
}

/** Places a fixed-height card, or answers null when the measured texts do not fit it. */
export function placeFixed(shape: CardShape, parts: Parts): Placed | null {
  const placed = stack(shape, parts);
  // A word wider than the column makes a text wider than its panel; the composite would clip it silently.
  const inner = shape.width - 2 * shape.padding - 2 * PANEL_PADDING - PANEL_EDGE;
  const widest = Math.max(parts.verse?.text.width ?? 0, parts.hadith?.text.width ?? 0);
  if (placed.frame + placed.wanted > shape.height || widest > inner) {
    return null;
  }
  return { width: shape.width, height: shape.height, layers: placed.layers(shape.height) };
}

/** Places a card that is as high as its texts need, never below its shape's own height. */
export function placeGrowing(shape: CardShape, parts: Parts): Placed {
  const placed = stack(shape, parts);
  const height = Math.max(shape.height, Math.ceil(placed.frame + placed.wanted));
  return { width: shape.width, height, layers: placed.layers(height) };
}

/**
 * Messaging apps show a link preview only under about 300 KB (v2 §25). The card
 * is a few flat colours and anti-aliased text on a dark ground, so a 256-colour
 * palette keeps every pixel it shows and roughly halves the bytes of a tall card.
 */
export const CARD_MAX_BYTES = 300_000;

export async function paint({ width, height, layers }: Placed): Promise<Buffer> {
  return sharp(background(width, height))
    .composite(
      layers.map((layer) => ({
        ...layer,
        left: Math.round(layer.left),
        top: Math.round(layer.top),
      }))
    )
    .png({ palette: true, compressionLevel: 6 })
    .toBuffer();
}
