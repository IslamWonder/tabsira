/**
 * Installing TABSIRA on the home screen.
 *
 * Chrome, Edge and Samsung Internet fire `beforeinstallprompt` once the app is
 * installable; it is kept here and replayed when the reader asks, so the
 * browser's own dialog only ever opens on a tap. Safari fires nothing: on an
 * iPhone or iPad the offer explains the two taps of the share sheet instead.
 *
 * The offer waits for real interest, never the first moments of a first visit
 * (tajriba: the scene first, nothing before it), as well-behaved web apps do:
 * a finished insight, a third page in a visit, 40 s on the site, or a return
 * visit. A dismissal is kept for DISMISS_DAYS. An app already opened from the
 * home screen is never offered. A quiet install button in the footer and in
 * the profile hub stays within reach whatever the offer was told.
 */

export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/** How the app can be installed here: by the browser's dialog, by Safari's share sheet, or not at all. */
export type InstallWay = 'prompt' | 'ios' | 'none';

export interface InstallState {
  way: InstallWay;
  /** Opened from the home screen, or installed during this visit. */
  installed: boolean;
}

/** Where the inline head script keeps a prompt fired before the app's code ran. */
const EARLY_PROMPT = '__tabsiraInstallPrompt';

/**
 * Runs inline in <head>: Chrome may fire `beforeinstallprompt` before React has
 * hydrated, and a prompt that nobody kept cannot be shown later. Plain ES5.
 */
export const INSTALL_CAPTURE_SCRIPT = `window.addEventListener("beforeinstallprompt",function(e){e.preventDefault();window.${EARLY_PROMPT}=e});`;

export const ENGAGED_KEY = 'tabsira.install.engaged';
export const DISMISSED_KEY = 'tabsira.install.dismissed';
export const FIRST_SEEN_KEY = 'tabsira.install.firstSeen';
export const DISMISS_DAYS = 30;
/** A visit this long after the first one is a return visit. */
export const RETURN_AFTER_MS = 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

let deferred: BeforeInstallPromptEvent | null = null;
let installedNow = false;
let listening = false;
const listeners = new Set<() => void>();
let snapshot: InstallState = { way: 'none', installed: false };

function standalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  return (
    nav.standalone === true ||
    (typeof window.matchMedia === 'function' &&
      window.matchMedia('(display-mode: standalone)').matches)
  );
}

/** An iPhone, an iPod or an iPad (which may present itself as a Mac with a touch screen). */
export function isAppleMobile(userAgent: string, touchPoints: number): boolean {
  return /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && touchPoints > 1);
}

function compute(): InstallState {
  const installed = installedNow || standalone();
  if (installed) {
    return { way: 'none', installed: true };
  }
  if (deferred !== null) {
    return { way: 'prompt', installed: false };
  }
  return {
    way: isAppleMobile(navigator.userAgent, navigator.maxTouchPoints ?? 0) ? 'ios' : 'none',
    installed: false,
  };
}

function changed(): void {
  const next = compute();
  if (next.way !== snapshot.way || next.installed !== snapshot.installed) {
    snapshot = next;
    for (const listener of listeners) {
      listener();
    }
  }
}

/** Starts listening for the browser's install events; called once, as early as the page allows. */
export function listenForInstall(): void {
  if (listening || typeof window === 'undefined') {
    return;
  }
  listening = true;
  const early = (window as unknown as Record<string, BeforeInstallPromptEvent | undefined>)[
    EARLY_PROMPT
  ];
  if (early !== undefined) {
    deferred = early;
  }
  window.addEventListener('beforeinstallprompt', (event) => {
    // Keep the browser's own mini-bar away: the offer comes at a moment of the reader's journey.
    event.preventDefault();
    deferred = event as BeforeInstallPromptEvent;
    changed();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    installedNow = true;
    changed();
  });
  // An iPhone or the installed app is known at once: tell whoever already reads the state.
  changed();
}

export function subscribeInstall(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function installSnapshot(): InstallState {
  return snapshot;
}

const SERVER_STATE: InstallState = { way: 'none', installed: false };
export function serverInstallSnapshot(): InstallState {
  return SERVER_STATE;
}

/** Opens the browser's install dialog; says whether the reader accepted. */
export async function promptInstall(): Promise<boolean> {
  const event = deferred;
  if (event === null) {
    return false;
  }
  // A deferred prompt can be shown once only.
  deferred = null;
  await event.prompt();
  const { outcome } = await event.userChoice;
  if (outcome === 'accepted') {
    installedNow = true;
  }
  changed();
  return outcome === 'accepted';
}

function readTime(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key);
    const value = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function writeTime(key: string, at: number): void {
  try {
    window.localStorage.setItem(key, String(at));
  } catch {
    // Private mode or a full store: the offer may come again next visit.
  }
}

/** Keeps the first visit's time; a later visit, RETURN_AFTER_MS on, counts as interest. */
export function noteVisit(now = Date.now()): void {
  const first = readTime(FIRST_SEEN_KEY);
  if (first === null) {
    writeTime(FIRST_SEEN_KEY, now);
  } else if (now - first >= RETURN_AFTER_MS) {
    markEngaged(now);
  }
}

/** The reader showed interest (a first insight, pages, time, a return): the app may be offered. */
export function markEngaged(now = Date.now()): void {
  if (readTime(ENGAGED_KEY) === null) {
    writeTime(ENGAGED_KEY, now);
  }
}

/** The reader said not now: no offer for DISMISS_DAYS. */
export function dismissOffer(now = Date.now()): void {
  writeTime(DISMISSED_KEY, now);
}

/** Whether to offer the app now: engaged, not dismissed lately, and installable here. */
export function mayOffer(state: InstallState, now = Date.now()): boolean {
  if (state.installed || state.way === 'none' || readTime(ENGAGED_KEY) === null) {
    return false;
  }
  const dismissed = readTime(DISMISSED_KEY);
  return dismissed === null || now - dismissed >= DISMISS_DAYS * DAY_MS;
}

/** For tests: forget the captured prompt and the listeners. */
export function resetInstall(): void {
  delete (window as unknown as Record<string, unknown>)[EARLY_PROMPT];
  deferred = null;
  installedNow = false;
  listening = false;
  listeners.clear();
  snapshot = { way: 'none', installed: false };
}
