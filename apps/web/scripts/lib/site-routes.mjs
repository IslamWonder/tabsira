// The routes the SEO checks walk. They mirror INDEXED_ROUTES, UNLISTED_ROUTES,
// PRIVATE_PATHS and AI_AGENTS of apps/web/src/lib (a unit test keeps the two
// in step), because a plain Node script cannot import TypeScript sources.

export const INDEXED_ROUTES = ['/', '/terms', '/privacy', '/support', '/sources'];

export const UNLISTED_ROUTES = [
  '/world',
  '/community',
  '/community/publish',
  '/atlas',
  '/atlas/publish',
  '/atlas/camera',
  '/me',
  '/offline',
  '/signin',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
];

export const PRIVATE_PATHS = ['/me', '/sky', '/admin', '/dev', '/api', '/consent'];

export const AI_AGENTS = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-SearchBot',
  'Claude-User',
  'Google-Extended',
  'GoogleOther',
  'PerplexityBot',
  'Perplexity-User',
  'Bingbot',
  'Applebot-Extended',
  'meta-externalagent',
  'Amazonbot',
  'CCBot',
  'DuckAssistBot',
  'MistralAI-User',
];

/** The production origin every built page must carry; a build that leaks a local one fails. */
export const PRODUCTION_ORIGIN = 'https://tabsira.me';

/** Icons the manifest must declare, as `sizes` values. */
export const MANIFEST_ICON_SIZES = ['192x192', '512x512'];
