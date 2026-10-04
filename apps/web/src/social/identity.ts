import type { Route } from 'next';
import { messages } from '@/messages';
import reserved from './reserved-handles.json';

/*
 * The rules of a public handle and name, as the API applies them
 * (apps/api/src/services/public_identity.py), checked before sending so a
 * mistake is learnt at the field (tajriba §3.5). The API stays the judge.
 */

const P = messages.community.identity.problems;

export const HANDLE_MIN = 3;
export const HANDLE_MAX = 30;
export const PUBLIC_NAME_MAX = 40;

// Latin or Arabic letters (no diacritics, no tatweel), digits and underscores, starting with a
// letter. Written as code points so the file holds no Arabic text (src/test/source-guards).
const HANDLE = /^[A-Za-z\u0621-\u063A\u0641-\u064A][A-Za-z0-9_\u0621-\u063A\u0641-\u064A]{2,29}$/;
// The names of the platform and its staff, in both scripts (src/social/reserved-handles.json).
const RESERVED = new Set<string>(reserved.exact);
const RESERVED_PREFIXES: readonly string[] = reserved.prefixes;
// An address or a link would put contact details on a public page; hidden characters would mislead.
const NAME_FORBIDDEN = /[@<>]|https?:|www\.|[\p{Cc}\p{Cf}\p{Cs}\p{Co}]/iu;

export function cleanHandle(raw: string): string {
  return raw.normalize('NFKC').trim();
}

export function handleProblem(raw: string): string | null {
  const handle = cleanHandle(raw);
  if (handle === '') {
    return P.handleMissing;
  }
  if (!HANDLE.test(handle)) {
    return P.handleShape;
  }
  const folded = handle.toLowerCase();
  if (RESERVED.has(folded) || RESERVED_PREFIXES.some((prefix) => folded.startsWith(prefix))) {
    return P.handleReserved;
  }
  return null;
}

export function cleanPublicName(raw: string): string {
  return raw.normalize('NFKC').split(/\s+/).filter(Boolean).join(' ');
}

export function publicNameProblem(raw: string): string | null {
  const name = cleanPublicName(raw);
  if (name === '') {
    return P.nameMissing;
  }
  if (Array.from(name).length > PUBLIC_NAME_MAX) {
    return P.nameLong;
  }
  return NAME_FORBIDDEN.test(name) ? P.nameInvalid : null;
}

/** The address of a member's public page, the handle percent-encoded as in the sitemap. */
export function profilePath(handle: string): Route {
  return `/u/${encodeURIComponent(handle)}` as Route;
}

export function postPath(postId: string): Route {
  return `/posts/${postId}` as Route;
}
