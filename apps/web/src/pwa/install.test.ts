import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installPrompt } from '@/test/install';
import {
  DISMISS_DAYS,
  DISMISSED_KEY,
  dismissOffer,
  ENGAGED_KEY,
  INSTALL_CAPTURE_SCRIPT,
  installSnapshot,
  isAppleMobile,
  listenForInstall,
  markEngaged,
  mayOffer,
  promptInstall,
  resetInstall,
  serverInstallSnapshot,
  subscribeInstall,
} from './install';

const DAY = 24 * 60 * 60 * 1000;

function setUserAgent(value: string, touchPoints = 0) {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(value);
  Object.defineProperty(navigator, 'maxTouchPoints', { value: touchPoints, configurable: true });
}

beforeEach(() => {
  resetInstall();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, 'standalone');
});

describe('install state', () => {
  it('keeps the browser prompt, stops its own bar, and replays it on demand', async () => {
    listenForInstall();
    listenForInstall();
    const changed = vi.fn();
    const stop = subscribeInstall(changed);
    const event = installPrompt();
    const prevent = vi.spyOn(event, 'preventDefault');
    window.dispatchEvent(event);

    expect(prevent).toHaveBeenCalled();
    expect(installSnapshot()).toEqual({ way: 'prompt', installed: false });
    expect(changed).toHaveBeenCalledOnce();
    expect(await promptInstall()).toBe(true);
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(installSnapshot()).toEqual({ way: 'none', installed: true });
    // Shown once only: nothing is left to show.
    expect(await promptInstall()).toBe(false);
    stop();
  });

  it('says nothing changed when the reader declines, and forgets the used prompt', async () => {
    listenForInstall();
    window.dispatchEvent(installPrompt('dismissed'));
    expect(await promptInstall()).toBe(false);
    expect(installSnapshot()).toEqual({ way: 'none', installed: false });
  });

  it('picks up a prompt the head script kept before the code ran', async () => {
    // A fresh copy of the module: the listeners that earlier tests left on `window`
    // belong to the first copy and cannot feed this one, so only the kept prompt can.
    vi.resetModules();
    const fresh = await import('./install');
    // Runs the exact inline script the layout ships, in the page's own realm: jsdom
    // does not execute a <script> a test appends.
    new Function(INSTALL_CAPTURE_SCRIPT)();
    const event = installPrompt();
    const prevent = vi.spyOn(event, 'preventDefault');
    window.dispatchEvent(event);
    expect(prevent).toHaveBeenCalled();

    fresh.listenForInstall();
    expect(fresh.installSnapshot().way).toBe('prompt');
    expect(await fresh.promptInstall()).toBe(true);
    expect(event.prompt).toHaveBeenCalledOnce();
    fresh.resetInstall();
  });

  it('is installed once the browser says so, or when opened from the home screen', () => {
    listenForInstall();
    window.dispatchEvent(installPrompt());
    window.dispatchEvent(new Event('appinstalled'));
    expect(installSnapshot()).toEqual({ way: 'none', installed: true });

    resetInstall();
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    listenForInstall();
    expect(installSnapshot().installed).toBe(true);
  });

  it('knows an iPhone and an iPad that calls itself a Mac, and nothing else', () => {
    expect(isAppleMobile('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)', 5)).toBe(true);
    expect(isAppleMobile('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 5)).toBe(true);
    expect(isAppleMobile('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 0)).toBe(false);
    expect(isAppleMobile('Mozilla/5.0 (X11; Linux x86_64)', 0)).toBe(false);
    setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)', 5);
    listenForInstall();
    expect(installSnapshot()).toEqual({ way: 'ios', installed: false });
  });

  it('starts empty on the server', () => {
    expect(serverInstallSnapshot()).toEqual({ way: 'none', installed: false });
  });
});

describe('when to offer', () => {
  const prompt = { way: 'prompt', installed: false } as const;

  it('waits for a finished insight, keeps its first date, and respects «ليس الآن» for a while', () => {
    expect(mayOffer(prompt, 1000)).toBe(false);
    markEngaged(1000);
    markEngaged(5000);
    expect(window.localStorage.getItem(ENGAGED_KEY)).toBe('1000');
    expect(mayOffer(prompt, 2000)).toBe(true);
    dismissOffer(2000);
    expect(mayOffer(prompt, 2000 + DAY)).toBe(false);
    expect(mayOffer(prompt, 2000 + DISMISS_DAYS * DAY)).toBe(true);
  });

  it('never offers where it cannot install or where it is installed', () => {
    markEngaged(1);
    expect(mayOffer({ way: 'none', installed: false }, 2)).toBe(false);
    expect(mayOffer({ way: 'none', installed: true }, 2)).toBe(false);
  });

  it('takes a damaged or blocked store for no record', () => {
    window.localStorage.setItem(ENGAGED_KEY, 'soon');
    expect(mayOffer(prompt, 2)).toBe(false);
    window.localStorage.setItem(ENGAGED_KEY, '1');
    window.localStorage.setItem(DISMISSED_KEY, 'never');
    expect(mayOffer(prompt, 2)).toBe(true);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => markEngaged(3)).not.toThrow();
    expect(() => dismissOffer(3)).not.toThrow();
    expect(mayOffer(prompt, 3)).toBe(false);
  });
});
