// Every icon and the default share image, generated from the designer's logo
// in brand/ (brand/README.md: no raster is drawn by hand). The brand files are
// read, never changed. Run after a change to them:
//
//   pnpm --filter @tabsira/web gen:icons
//
// Icons sit on unknown browser chrome, so each carries its own night ground
// (#0B1210) with the mark in brand gold (#B28B38, 5.99:1 on night):
//
//   public/favicon.ico              16, 32 and 48 px, PNG inside ICO, night disc
//   public/icon.svg                 the scalable favicon, night disc
//   public/icons/icon-192.png       purpose "any", night disc
//   public/icons/icon-512.png       purpose "any", night disc
//   public/icons/maskable-512.png   purpose "maskable", full bleed, mark in the safe zone
//   public/icons/apple-icon.png     180 px, opaque square (iOS rounds it itself)
//   public/icons/mstile-150.png     Windows tile, with public/browserconfig.xml
//   public/share/default.jpg        1200x630 share card: the full logo and the tagline
//   src/components/brand/logo-paths.ts  the outlines, for the inline <Logo> (currentColor)
//   ../api/src/templates/email/logo.png  the full logo in deep gold for the mails' white card,
//                                   144 px high (shown at 72), transparent; mail clients show no SVG
//
// "Round-safe": the round mark always fits inside the circle a platform may
// crop the icon to, with a margin.

import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BRAND = path.resolve(WEB, '../../brand');
const PUBLIC = path.join(WEB, 'public');
const PATHS_MODULE = path.join(WEB, 'src/components/brand/logo-paths.ts');
const NIGHT = '#0B1210';
const GOLD = '#B28B38';
const IVORY = '#EEF3EF';
const TAGLINE = 'انظر إلى العالم بعين الوحي';
const NAME = 'تبصرة';
// One face for the card (docs/SEO.md §2), from the pinned OFL package; WOFF, which FreeType reads.
const CARD_FONT = path.join(
  WEB,
  'node_modules/@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-600-normal.woff'
);

/** The viewBox and the outlines of a brand file, exactly as drawn. */
async function readBrand(file) {
  const text = await readFile(path.join(BRAND, file), 'utf8');
  const viewBox = /viewBox="([^"]+)"/.exec(text)?.[1];
  const paths = Array.from(text.matchAll(/<path d="([^"]+)"\s*\/>/g), (match) => match[1]);
  if (viewBox === undefined || paths.length === 0) {
    throw new Error(`${file}: no viewBox or no path found`);
  }
  const [, , width, height] = viewBox.split(/\s+/).map(Number);
  return { viewBox, width, height, paths };
}

/** The outlines scaled to `box` pixels wide, their top-left corner at (x, y). */
function placed(shape, { x, y, box, fill = GOLD }) {
  const outlines = shape.paths.map((d) => `<path d="${d}"/>`).join('');
  const scale = box / shape.width;
  return `<g fill="${fill}" transform="translate(${x} ${y}) scale(${scale})">${outlines}</g>`;
}

/**
 * A square icon of `size`: the night ground as a disc or a full square, and
 * the mark at `ratio` of the side, centred.
 */
function iconSvg(mark, { size, ground, ratio }) {
  const box = size * ratio;
  const offset = (size - box) / 2;
  const half = size / 2;
  const back =
    ground === 'disc'
      ? `<circle cx="${half}" cy="${half}" r="${half}" fill="${NIGHT}"/>`
      : `<rect width="${size}" height="${size}" fill="${NIGHT}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img"><title>${NAME}</title>${back}${placed(mark, { x: offset, y: offset, box })}</svg>`;
}

async function png(svg, size) {
  return sharp(Buffer.from(svg), { density: 72 * Math.max(1, 512 / size) })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toBuffer();
}

/** An ICO file holding PNG images (read by every current browser). */
function ico(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const directory = Buffer.alloc(16 * images.length);
  let offset = header.length + directory.length;
  images.forEach(({ size, data }, index) => {
    const at = index * 16;
    directory.writeUInt8(size, at);
    directory.writeUInt8(size, at + 1);
    directory.writeUInt8(0, at + 2);
    directory.writeUInt8(0, at + 3);
    directory.writeUInt16LE(1, at + 4);
    directory.writeUInt16LE(32, at + 6);
    directory.writeUInt32LE(data.length, at + 8);
    directory.writeUInt32LE(offset, at + 12);
    offset += data.length;
  });
  return Buffer.concat([header, directory, ...images.map((image) => image.data)]);
}

/** The share card: night, two soft glows, a thin gold frame, the full logo and the tagline. */
async function shareCard(logo) {
  const width = 1200;
  const height = 630;
  const logoHeight = 330;
  const logoWidth = (logoHeight * logo.width) / logo.height;
  const ground = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <defs>
    <radialGradient id="emerald" cx="85%" cy="0%" r="70%">
      <stop offset="0" stop-color="#1F9E6E" stop-opacity="0.22"/>
      <stop offset="1" stop-color="#1F9E6E" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="gold" cx="50%" cy="42%" r="45%">
      <stop offset="0" stop-color="#E6C77F" stop-opacity="0.12"/>
      <stop offset="1" stop-color="#E6C77F" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${width}" height="${height}" fill="${NIGHT}"/>
  <rect width="${width}" height="${height}" fill="url(#emerald)"/>
  <rect width="${width}" height="${height}" fill="url(#gold)"/>
  <rect x="24" y="24" width="${width - 48}" height="${height - 48}" rx="22" fill="none" stroke="${GOLD}" stroke-opacity="0.55"/>
  <rect x="31" y="31" width="${width - 62}" height="${height - 62}" rx="17" fill="none" stroke="${GOLD}" stroke-opacity="0.22"/>
  ${placed(logo, { x: (width - logoWidth) / 2, y: 64, box: logoWidth })}
</svg>`;
  const tagline = await sharp({
    text: {
      text: `<span foreground="${IVORY}">${TAGLINE}</span>`,
      font: 'IBM Plex Sans Arabic SemiBold, 50',
      fontfile: CARD_FONT,
      rgba: true,
      dpi: 72,
    },
  })
    .png()
    .toBuffer({ resolveWithObject: true });
  return sharp(Buffer.from(ground))
    .composite([
      {
        input: tagline.data,
        left: Math.round((width - tagline.info.width) / 2),
        top: 64 + logoHeight + 56,
      },
    ])
    .jpeg({ quality: 86, mozjpeg: true })
    .toBuffer();
}

/** The outlines as a TypeScript module, so the interface draws the logo inline in currentColor. */
function pathsModule(mark, logo) {
  const list = (paths) => paths.map((d) => `    '${d}',`).join('\n');
  return `// Generated by scripts/make-icons.mjs from brand/tabsira-mark.svg and
// brand/tabsira-logo.svg: the designer's outlines, unchanged. Do not edit;
// run \`pnpm --filter @tabsira/web gen:icons\` after a change in brand/.

export const MARK = {
  viewBox: '${mark.viewBox}',
  paths: [
${list(mark.paths)}
  ],
} as const;

export const LOGO = {
  viewBox: '${logo.viewBox}',
  paths: [
${list(logo.paths)}
  ],
} as const;
`;
}

const mark = await readBrand('tabsira-mark-gold.svg');
const logo = await readBrand('tabsira-logo-gold.svg');
const inlineMark = await readBrand('tabsira-mark.svg');
const inlineLogo = await readBrand('tabsira-logo.svg');

const disc = { ground: 'disc', ratio: 0.74 };
await mkdir(path.join(PUBLIC, 'icons'), { recursive: true });
await mkdir(path.join(PUBLIC, 'share'), { recursive: true });

const favicons = await Promise.all(
  [16, 32, 48].map(async (size) => ({
    size,
    // Tiny sizes need every pixel: the mark fills more of the disc.
    data: await png(iconSvg(mark, { size, ground: 'disc', ratio: 0.84 }), size),
  }))
);
await writeFile(path.join(PUBLIC, 'favicon.ico'), ico(favicons));
await writeFile(path.join(PUBLIC, 'icon.svg'), `${iconSvg(mark, { size: 512, ...disc })}\n`);
for (const size of [192, 512]) {
  await writeFile(
    path.join(PUBLIC, `icons/icon-${size}.png`),
    await png(iconSvg(mark, { size, ...disc }), size)
  );
}
// Maskable icons may be cropped to a circle of 80 % of their side: the mark stays well inside.
await writeFile(
  path.join(PUBLIC, 'icons/maskable-512.png'),
  await png(iconSvg(mark, { size: 512, ground: 'square', ratio: 0.56 }), 512)
);
await writeFile(
  path.join(PUBLIC, 'icons/apple-icon.png'),
  await png(iconSvg(mark, { size: 180, ground: 'square', ratio: 0.7 }), 180)
);
await writeFile(
  path.join(PUBLIC, 'icons/mstile-150.png'),
  await png(iconSvg(mark, { size: 150, ground: 'square', ratio: 0.6 }), 150)
);
await writeFile(
  path.join(PUBLIC, 'browserconfig.xml'),
  `<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
  <msapplication>
    <tile>
      <square150x150logo src="/icons/mstile-150.png"/>
      <TileColor>${NIGHT}</TileColor>
    </tile>
  </msapplication>
</browserconfig>
`
);
await writeFile(path.join(PUBLIC, 'share/default.jpg'), await shareCard(logo));
const MAIL_LOGO = path.resolve(WEB, '../api/src/templates/email/logo.png');
await writeFile(
  MAIL_LOGO,
  await sharp(await readFile(path.join(BRAND, 'tabsira-logo-deep-gold.svg')), { density: 288 })
    .resize({ height: 144 })
    .png({ compressionLevel: 9 })
    .toBuffer()
);
await writeFile(PATHS_MODULE, pathsModule(inlineMark, inlineLogo));
// The generated module is committed: give it the layout the format check expects.
execFileSync('pnpm', ['exec', 'biome', 'format', '--write', PATHS_MODULE], { stdio: 'ignore' });
console.log('Icons, share card and logo outlines written from brand/.');
