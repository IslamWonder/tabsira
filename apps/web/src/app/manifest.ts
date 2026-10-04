import type { MetadataRoute } from 'next';
import { messages, siteLanguage } from '@/messages';
import { THEME_BACKGROUND } from '@/theme/colors';

/**
 * The installable app. Its icons are drawn from the logo in brand/ by
 * scripts/make-icons.mjs, each declared at its exact size. No orientation
 * lock: the app must work held either way (WCAG 1.3.4).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: messages.meta.siteName,
    short_name: messages.meta.siteName,
    description: messages.meta.shortDescription,
    lang: siteLanguage.tag,
    dir: siteLanguage.dir,
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
        src: '/icons/maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
