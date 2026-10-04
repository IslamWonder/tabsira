import { SERVER_API_TIMEOUT_MS, serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { AtlasEntry, AtlasPlace } from './types';

/*
 * What the web server reads to write a public atlas page's metadata: the
 * entry or the place as a stranger sees it, with no cookie. A short timeout,
 * so a slow API never holds the page.
 */

function client() {
  return createApiClient({ baseUrl: serverApiOrigin() });
}

const timeout = () => AbortSignal.timeout(SERVER_API_TIMEOUT_MS);

export function entryOnServer(entryId: string): Promise<Result<AtlasEntry>> {
  return attempt(
    client().GET('/atlas/entries/{entry_id}', {
      params: { path: { entry_id: entryId } },
      signal: timeout(),
    })
  );
}

export function placeOnServer(geonameId: number): Promise<Result<AtlasPlace>> {
  return attempt(
    client().GET('/atlas/places/{geoname_id}', {
      params: { path: { geoname_id: geonameId } },
      signal: timeout(),
    })
  );
}
