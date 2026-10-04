// TEMPORARY icons. The designer delivers the logo (master prompt §20); until
// then this script draws every size from one simple glyph: an eight-point star
// in gold on the night ground of direction C, with a glowing point at its
// heart (the insight point of the scene). No text, so no font is needed and
// the output is the same on every machine. When the real logo arrives, replace
// glyphSvg() and run it again: pnpm --filter @tabsira/web gen:icons
//
// Writes public/icons/{icon-192,icon-512,icon-maskable-512,apple-touch-icon}.png
// and public/favicon.ico (16, 32 and 48 px, PNG inside ICO).

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const PUBLIC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public');

/** The glyph on a 512 grid. `radius` rounds the ground; `scale` shrinks the star for maskable safe zones. */
function glyphSvg({ radius, scale }) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <radialGradient id="ground" cx="50%" cy="36%" r="80%">
      <stop offset="0" stop-color="#1c3a31"/>
      <stop offset="1" stop-color="#0b1210"/>
    </radialGradient>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#fff4d6"/>
      <stop offset="0.35" stop-color="#e6c77f" stop-opacity="0.9"/>
      <stop offset="0.7" stop-color="#3fd69a" stop-opacity="0.25"/>
      <stop offset="1" stop-color="#3fd69a" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="512" height="512" rx="${radius}" fill="url(#ground)"/>
  <g transform="translate(256 256) scale(${scale})" fill="none" stroke="#e6c77f" stroke-width="12" stroke-linejoin="round">
    <rect x="-120" y="-120" width="240" height="240"/>
    <rect x="-120" y="-120" width="240" height="240" transform="rotate(45)"/>
    <circle r="104" fill="url(#glow)" stroke="none"/>
    <circle r="28" fill="#fff4d6" stroke="none"/>
  </g>
</svg>`;
}

async function png(size, options) {
  return sharp(Buffer.from(glyphSvg(options)))
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toBuffer();
}

/** An ICO file holding PNG images (supported by every current browser). */
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

const rounded = { radius: 112, scale: 1 };
// Maskable icons are cropped to a circle of 80 % of their width: full-bleed ground, smaller star.
const maskable = { radius: 0, scale: 0.78 };
// iOS rounds the corners itself and refuses transparency.
const square = { radius: 0, scale: 0.9 };

await mkdir(path.join(PUBLIC, 'icons'), { recursive: true });
await writeFile(path.join(PUBLIC, 'icons/icon-192.png'), await png(192, rounded));
await writeFile(path.join(PUBLIC, 'icons/icon-512.png'), await png(512, rounded));
await writeFile(path.join(PUBLIC, 'icons/icon-maskable-512.png'), await png(512, maskable));
await writeFile(path.join(PUBLIC, 'icons/apple-touch-icon.png'), await png(180, square));
const favicons = await Promise.all(
  [16, 32, 48].map(async (size) => ({ size, data: await png(size, rounded) }))
);
await writeFile(path.join(PUBLIC, 'favicon.ico'), ico(favicons));
console.log('TEMPORARY icons written to public/icons and public/favicon.ico');
