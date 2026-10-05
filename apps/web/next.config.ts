import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parseEnv } from 'node:util';
import type { NextConfig } from 'next';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants';
import { mergeEnv, resolvePublicEnv } from './src/config/public-env';
import { QURAN_SOURCE, TEXT_SOURCES } from './src/lib/share-card/fonts';

const REPO_ROOT = path.resolve(__dirname, '../..');

// The repository keeps one .env at its root (the API reads it too); Next.js on
// its own would only look in apps/web. Values already in the environment win,
// so CI and deploy scripts stay in control.
function readRootEnv(): Record<string, string> {
  try {
    return { ...parseEnv(readFileSync(path.join(REPO_ROOT, '.env'), 'utf8')) } as Record<
      string,
      string
    >;
  } catch {
    return {};
  }
}

export default function nextConfig(phase: string): NextConfig {
  // Throws, and so fails the build, when a production build points at a
  // development host: NEXT_PUBLIC_* values are baked into every page.
  const publicEnv = resolvePublicEnv(mergeEnv(readRootEnv(), process.env));
  const isDevServer = phase === PHASE_DEVELOPMENT_SERVER;

  return {
    output: 'standalone',
    outputFileTracingRoot: REPO_ROOT,
    // The share card reads its fonts from disk at request time (src/lib/share-card/fonts.ts),
    // a path the tracer cannot follow; name the files so a standalone build carries them.
    outputFileTracingIncludes: {
      '/insights/[id]/card': [QURAN_SOURCE, ...TEXT_SOURCES].map((file) => `./${file}`),
    },
    // sharp is already a dependency; AVIF trims the landing cards further.
    images: { formats: ['image/avif', 'image/webp'] },
    turbopack: { root: REPO_ROOT },
    poweredByHeader: false,
    // Our rules live in the root AGENTS.md; stop `next dev` writing its own copies.
    agentRules: false,
    reactStrictMode: true,
    // The floating dev badge sits on the phone navigation; the terminal reports the same.
    devIndicators: false,
    typedRoutes: true,
    // `next dev` is reached through the local nginx (http://tabsira.test); its
    // hot reload and dev assets refuse other origins unless they are listed.
    allowedDevOrigins: isDevServer ? [new URL(publicEnv.siteUrl).hostname] : [],
    // The component gallery (src/app/dev/ui/page.dev.tsx) is a route only under
    // `next dev`; a production build does not contain it at all.
    pageExtensions: isDevServer ? ['dev.tsx', 'tsx', 'ts'] : ['tsx', 'ts'],
    env: {
      NEXT_PUBLIC_SITE_URL: publicEnv.siteUrl,
      NEXT_PUBLIC_API_URL: publicEnv.apiUrl,
      NEXT_PUBLIC_PROFILE_QUESTIONS_MAX: String(publicEnv.profileQuestionsMax),
    },
    async redirects() {
      return [
        // The API's Google callback reports a failure at /login?error=<code>
        // (docs/AUTH.md); the sign-in page lives at /signin. Temporary, so the
        // API can point at /signin directly later. The query string follows.
        { source: '/login', destination: '/signin', permanent: false },
      ];
    },
    async headers() {
      return [
        {
          // A stale service worker would pin users to an old release.
          source: '/sw.js',
          headers: [
            { key: 'Content-Type', value: 'application/javascript; charset=utf-8' },
            { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
            { key: 'Service-Worker-Allowed', value: '/' },
          ],
        },
        // The decorative pictures are the heaviest files in the app (the world
        // landscape alone is ~660 KB) and Next would otherwise revalidate them
        // on every visit. They are served for a year instead: any change to one
        // of them is a new file name (as with the courtyard picture). Icons and
        // the share card stay revalidating — the service worker precaches and
        // link previews name them, so a pinned stale copy would be invisible.
        ...['/world/:path*', '/landing/:path*', '/scene/:path*'].map((source) => ({
          source,
          headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
        })),
      ];
    },
  };
}
