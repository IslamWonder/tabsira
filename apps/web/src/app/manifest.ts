import type { MetadataRoute } from 'next';
import { ar } from '@/messages/ar';
import { THEME_BACKGROUND } from '@/theme/colors';

/**
 * The installable app. The icons are TEMPORARY, drawn by scripts/make-icons.mjs
 * from a simple glyph until the designer delivers the logo (master prompt §20).
 * No orientation lock: the app must work held either way (WCAG 1.3.4).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: ar.meta.siteName,
    short_name: ar.meta.siteName,
    description: ar.meta.shortDescription,
    lang: 'ar',
    dir: 'rtl',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    // The night of direction C is the brand's ground: the splash screen uses it.
    background_color: THEME_BACKGROUND.dark,
    theme_color: THEME_BACKGROUND.dark,
    categories: ['education', 'lifestyle'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/icon-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
