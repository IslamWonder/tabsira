/** One header rule of next.config's `headers()`. */
export interface HeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

/** The folders of public/ that hold the decorative pictures, and nothing else. */
export const PICTURE_FOLDERS = ['world', 'landing', 'scene'] as const;

const PICTURE = '[^/]+\\.(?:webp|avif|png|jpe?g)';

/**
 * The decorative pictures are the heaviest files in the app (the world
 * landscape alone is ~660 KB) and Next would otherwise revalidate them on every
 * visit. They are served for a year instead: any change to one of them is a new
 * file name (as with the courtyard picture). Each rule names picture files
 * only: a folder pattern would also match the route of the same name (`/world`
 * is the reader's own page) and pin that page for a year in every cache.
 */
export const PICTURE_CACHE_RULES: readonly HeaderRule[] = PICTURE_FOLDERS.map((folder) => ({
  source: `/${folder}/:file(${PICTURE})`,
  headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
}));
