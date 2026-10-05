/*
 * The two pictures of layout 1 (data/world/layout-1.json): the ground and the
 * clouds over it, from the owners' world kit, served from this site only.
 */
export const LANDSCAPE_SRC = '/world/landscape-1.webp';
export const CLOUDS_SRC = '/world/clouds-1.webp';

/** Load a picture to draw on a canvas; null when it could not be loaded. */
export function loadPicture(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}
