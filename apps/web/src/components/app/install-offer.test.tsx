import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { DISMISSED_KEY, ENGAGED_KEY, resetInstall } from '@/pwa/install';
import { ENGAGED_EVENT } from '@/pwa/use-install';
import { installPrompt } from '@/test/install';
import { InstallOffer, OFFER_DELAY_MS } from './install-offer';

const T = messages.install;

beforeEach(() => {
  resetInstall();
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function offer() {
  return screen.queryByRole('region', { name: T.region });
}

describe('InstallOffer', () => {
  it('says nothing on a first visit, even where the browser could install', () => {
    render(<InstallOffer />);
    act(() => {
      window.dispatchEvent(installPrompt());
    });
    expect(offer()).toBeNull();
  });

  it('offers the app a moment after a first insight is done, and opens the browser dialog', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<InstallOffer />);
    const event = installPrompt();
    act(() => {
      window.dispatchEvent(event);
    });
    act(() => {
      window.localStorage.setItem(ENGAGED_KEY, String(Date.now()));
      window.dispatchEvent(new Event(ENGAGED_EVENT));
    });
    expect(offer()).toBeNull();
    act(() => {
      vi.advanceTimersByTime(OFFER_DELAY_MS);
    });
    expect(offer()).not.toBeNull();
    await userEvent.click(screen.getByRole('button', { name: T.install }));
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(offer()).toBeNull();
  });

  it('comes back on a later visit, and keeps «ليس الآن» for a while', async () => {
    window.localStorage.setItem(ENGAGED_KEY, '1');
    render(<InstallOffer />);
    act(() => {
      window.dispatchEvent(installPrompt());
    });
    expect(offer()).not.toBeNull();
    await userEvent.click(screen.getByRole('button', { name: T.later }));
    expect(offer()).toBeNull();
    expect(window.localStorage.getItem(DISMISSED_KEY)).not.toBeNull();
  });

  it('shows the share-sheet steps on an iPhone, then rests', async () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)'
    );
    window.localStorage.setItem(ENGAGED_KEY, '1');
    render(<InstallOffer />);
    await userEvent.click(screen.getByRole('button', { name: T.iosShow }));
    const steps = screen.getByRole('dialog', { name: T.iosTitle });
    expect(steps).toHaveTextContent('إضافة إلى الشاشة الرئيسية');
    await userEvent.click(screen.getByRole('button', { name: T.gotIt }));
    expect(offer()).toBeNull();
    expect(window.localStorage.getItem(DISMISSED_KEY)).not.toBeNull();
  });

  it('never shows in the installed app', () => {
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    window.localStorage.setItem(ENGAGED_KEY, '1');
    render(<InstallOffer />);
    expect(offer()).toBeNull();
    Reflect.deleteProperty(navigator, 'standalone');
  });
});
