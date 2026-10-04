import { expireCookies } from './cookies';
import { flushEvents } from './events';

/**
 * Google Analytics 4 (owner decisions 28 and 31). Nothing here runs before the
 * analytics category is accepted: `<AnalyticsTags>` calls it from inside a
 * `<ConsentGate>`. The Consent Mode defaults script of <head> must have run
 * (it defines `gtag`); without it nothing is loaded.
 */

export const GA_SCRIPT_ID = 'ga4-tag';
const GA_COOKIES = /^_ga(_.*)?$|^_gid$|^_gat(_.*)?$/;

type GtagFunction = (...args: unknown[]) => void;
type GoogleWindow = Window & {
  gtag?: GtagFunction;
  [flag: `ga-disable-${string}`]: boolean | undefined;
};

function googleWindow(): GoogleWindow {
  return window as unknown as GoogleWindow;
}

/** Only the origin of the referrer: a query string of another site is never passed on. */
function referrerOrigin(): string | undefined {
  return document.referrer === '' ? undefined : `${new URL(document.referrer).origin}/`;
}

/** Without query string or fragment: the page's own path, nothing a visitor typed. */
function pageLocation(): string {
  return `${window.location.origin}${window.location.pathname}`;
}

export function startGoogleAnalytics(id: string): void {
  const win = googleWindow();
  const gtag = win.gtag;
  if (typeof gtag !== 'function') {
    return;
  }
  win[`ga-disable-${id}`] = false;
  gtag('consent', 'update', { analytics_storage: 'granted' });
  if (document.getElementById(GA_SCRIPT_ID) === null) {
    gtag('js', new Date());
    gtag('config', id, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      page_location: pageLocation(),
      page_referrer: referrerOrigin(),
    });
    const script = document.createElement('script');
    script.id = GA_SCRIPT_ID;
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
    document.head.appendChild(script);
  }
  flushEvents();
}

/** The page is one where no tool runs (sign-in, account): Google's own opt-out switch, until the next page. */
export function pauseGoogleAnalytics(id: string): void {
  googleWindow()[`ga-disable-${id}`] = true;
}

/** The visitor withdrew: stop, deny storage and delete what was written. */
export function stopGoogleAnalytics(id: string): void {
  const win = googleWindow();
  win[`ga-disable-${id}`] = true;
  if (typeof win.gtag === 'function') {
    win.gtag('consent', 'update', { analytics_storage: 'denied' });
  }
  expireCookies(GA_COOKIES);
}
