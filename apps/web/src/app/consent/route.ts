import { NextResponse } from 'next/server';
import { safeNextPath } from '@/account/links';
import { ACCEPT_ALL, type ConsentChoices, REJECT_ALL } from '@/consent/contract';
import {
  CONSENT_COOKIE,
  CONSENT_MAX_AGE_SECONDS,
  DISMISSED_COOKIE,
  VIEW_COOKIE,
  VIEW_MAX_AGE_SECONDS,
  validConsentId,
} from '@/consent/cookie';
import { postOnServer } from '@/consent/server-api';
import { siteOrigin } from '@/lib/site';

/*
 * The cookie choice without JavaScript (owner decision 32): the consent
 * screen is a real form that posts here. Its buttons say what to do; the
 * choice is recorded through the API, the id is kept in the consent cookie,
 * and the browser goes back to the page it came from (303). With JavaScript
 * the page does the same itself and never comes here.
 */

function cookieOf(request: Request, name: string): string | null {
  const match = new RegExp(`(?:^|;\\s*)${name}=([^;]*)`).exec(request.headers.get('cookie') ?? '');
  return match === null ? null : decodeURIComponent(match[1] as string);
}

/** A cross-site page must not choose for the visitor: same rule as the API's Origin check. */
function fromThisSite(request: Request): boolean {
  const origin = request.headers.get('origin');
  if (origin !== null) {
    return origin === siteOrigin().origin;
  }
  const site = request.headers.get('sec-fetch-site');
  return site === null || site === 'same-origin' || site === 'none';
}

function choicesOf(choice: FormDataEntryValue | null, form: FormData): ConsentChoices | null {
  if (choice === 'accept') {
    return ACCEPT_ALL;
  }
  if (choice === 'reject') {
    return REJECT_ALL;
  }
  if (choice === 'save') {
    return { necessary: true, analytics: form.has('analytics'), behaviour: form.has('behaviour') };
  }
  return null;
}

export async function POST(request: Request): Promise<Response> {
  if (!fromThisSite(request)) {
    return new Response(null, { status: 403 });
  }
  const form = await request.formData();
  const back = new URL(safeNextPath(String(form.get('return') ?? '/')), siteOrigin());
  const response = NextResponse.redirect(back, 303);
  const secure = back.protocol === 'https:';
  const cookie = { path: '/', sameSite: 'lax' as const, secure };
  const choice = form.get('choice');

  if (choice === 'customise') {
    response.cookies.set(VIEW_COOKIE, 'customise', { ...cookie, maxAge: VIEW_MAX_AGE_SECONDS });
    return response;
  }
  if (choice === 'back') {
    response.cookies.set(VIEW_COOKIE, '', { ...cookie, maxAge: 0 });
    return response;
  }
  const choices = choicesOf(choice, form);
  if (choices === null) {
    return new Response(null, { status: 400 });
  }

  const previous = validConsentId(cookieOf(request, CONSENT_COOKIE));
  const version = form.get('policy_version');
  const result = await postOnServer(
    {
      ...(previous === null ? {} : { consent_id: previous }),
      ...(typeof version === 'string' && version !== '' ? { policy_version: version } : {}),
      ...choices,
    },
    {
      userAgent: request.headers.get('user-agent'),
      // What the browser sends the API itself (the session cookie is shared by both).
      cookies: request.headers.get('cookie'),
    }
  );
  response.cookies.set(VIEW_COOKIE, '', { ...cookie, maxAge: 0 });
  if (result.ok) {
    response.cookies.set(CONSENT_COOKIE, result.data.consent_id, {
      ...cookie,
      maxAge: CONSENT_MAX_AGE_SECONDS,
    });
    response.cookies.set(DISMISSED_COOKIE, '', { ...cookie, maxAge: 0 });
  } else if (choices === REJECT_ALL) {
    // Refusing always closes the screen; an earlier yes must not come back.
    response.cookies.set(CONSENT_COOKIE, '', { ...cookie, maxAge: 0 });
    response.cookies.set(DISMISSED_COOKIE, '1', cookie);
  } else {
    response.cookies.set(VIEW_COOKIE, 'failed', { ...cookie, maxAge: VIEW_MAX_AGE_SECONDS });
  }
  return response;
}
