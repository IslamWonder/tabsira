import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { resetInstall } from '@/pwa/install';
import { installPrompt } from '@/test/install';
import { AppSection } from './app-section';

const T = messages.install;

beforeEach(() => {
  resetInstall();
});

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, 'standalone');
});

describe('AppSection', () => {
  it('installs through the browser dialog and says it is done', async () => {
    render(<AppSection />);
    act(() => {
      window.dispatchEvent(installPrompt());
    });
    await userEvent.click(screen.getByRole('button', { name: T.meInstall }));
    expect(screen.getByRole('status')).toHaveTextContent(T.accepted);
    expect(screen.queryByRole('button', { name: T.meInstall })).toBeNull();
  });

  it('keeps the button when the reader declines', async () => {
    render(<AppSection />);
    act(() => {
      window.dispatchEvent(installPrompt('dismissed'));
    });
    await userEvent.click(screen.getByRole('button', { name: T.meInstall }));
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
    expect(screen.getByText(T.meUnsupported)).toBeInTheDocument();
  });

  it('shows the share-sheet steps on an iPhone', async () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)'
    );
    render(<AppSection />);
    await userEvent.click(screen.getByRole('button', { name: T.meInstall }));
    expect(screen.getByRole('dialog', { name: T.iosTitle })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: T.gotIt }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('says the app is installed, or that this browser cannot install it', () => {
    const { unmount } = render(<AppSection />);
    expect(screen.getByText(T.meUnsupported)).toBeInTheDocument();
    unmount();
    resetInstall();
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    render(<AppSection />);
    expect(screen.getByText(T.meInstalled)).toBeInTheDocument();
  });
});
