/**
 * The two public addresses the browser needs, resolved once, at build time.
 *
 * `NEXT_PUBLIC_*` values are baked into every page and every share tag, so a
 * build made with a local URL would carry it to production. `resolvePublicEnv`
 * therefore throws for a production build that points at a development host,
 * and next.config.ts lets that error fail the build.
 *
 * `NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_API_URL` win; without them the
 * repository's shared `SITE_URL` and `API_URL` (root .env, also read by the
 * API) are used. The `.test` defaults apply outside production only.
 */

export type Environment = 'development' | 'test' | 'production';

export interface PublicEnv {
  readonly environment: Environment;
  /** Origin of the web app, without a trailing slash. */
  readonly siteUrl: string;
  /** Origin of the API, without a trailing slash. */
  readonly apiUrl: string;
}

export type EnvSource = Readonly<Record<string, string | undefined>>;

export const DEVELOPMENT_SITE_URL = 'https://tabsira.test';
export const DEVELOPMENT_API_URL = 'https://api.tabsira.test';

const ENV_KEYS = [
  'ENVIRONMENT',
  'SITE_URL',
  'API_URL',
  'NEXT_PUBLIC_SITE_URL',
  'NEXT_PUBLIC_API_URL',
] as const;

export class PublicEnvError extends Error {
  override readonly name = 'PublicEnvError';
}

/** The keys this module reads, from the root .env file and then the process environment. */
export function mergeEnv(fileValues: EnvSource, processEnv: EnvSource): EnvSource {
  const merged: Record<string, string | undefined> = {};
  for (const key of ENV_KEYS) {
    merged[key] = processEnv[key] ?? fileValues[key];
  }
  return merged;
}

export function resolveEnvironment(value: string | undefined): Environment {
  if (value === undefined || value === '') {
    return 'development';
  }
  if (value === 'development' || value === 'test' || value === 'production') {
    return value;
  }
  throw new PublicEnvError(`ENVIRONMENT must be development, test or production, not "${value}".`);
}

function isDevelopmentHost(hostname: string): boolean {
  return (
    hostname === 'localhost' ||
    hostname.endsWith('.localhost') ||
    hostname === 'test' ||
    hostname.endsWith('.test') ||
    hostname === '127.0.0.1' ||
    hostname === '[::1]'
  );
}

/** A validated origin (scheme, host, port), or a PublicEnvError naming the key. */
export function resolveOrigin(
  name: string,
  value: string | undefined,
  developmentDefault: string,
  environment: Environment
): string {
  const production = environment === 'production';
  const raw = value?.trim() || (production ? '' : developmentDefault);
  if (raw === '') {
    throw new PublicEnvError(`${name} is required for a production build.`);
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new PublicEnvError(`${name} is not a URL: "${raw}".`);
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new PublicEnvError(`${name} must use https: "${raw}".`);
  }
  if (url.pathname !== '/' || url.search !== '' || url.hash !== '' || url.username !== '') {
    throw new PublicEnvError(
      `${name} must be an origin with no path, query or credentials: "${raw}".`
    );
  }
  if (production && url.protocol !== 'https:') {
    throw new PublicEnvError(`${name} must use https in production: "${raw}".`);
  }
  if (production && isDevelopmentHost(url.hostname)) {
    throw new PublicEnvError(
      `${name} points to the development host ${url.hostname} in a production build.`
    );
  }
  return url.origin;
}

export function resolvePublicEnv(source: EnvSource): PublicEnv {
  const environment = resolveEnvironment(source.ENVIRONMENT);
  return {
    environment,
    siteUrl: resolveOrigin(
      'NEXT_PUBLIC_SITE_URL',
      source.NEXT_PUBLIC_SITE_URL || source.SITE_URL,
      DEVELOPMENT_SITE_URL,
      environment
    ),
    apiUrl: resolveOrigin(
      'NEXT_PUBLIC_API_URL',
      source.NEXT_PUBLIC_API_URL || source.API_URL,
      DEVELOPMENT_API_URL,
      environment
    ),
  };
}
