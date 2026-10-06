import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { resetInstall } from '@/pwa/install';
import { installPrompt } from '@/test/install';
import { InstallLink } from './install-link';

const T = messages.install;
const list = (ui: React.ReactNode) => render(<ul>{ui}</ul>);

beforeEach(() => {
  resetInstall();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('InstallLink', () => {
  it('opens the browser dialog from the first visit, wherever the browser can install', async () => {
    const { container } = list(<InstallLink className="quiet" />);
    expect(container.querySelector('li')).toBeNull();
    const event = installPrompt();
    act(() => {
      window.dispatchEvent(event);
    });
    await userEvent.click(screen.getByRole('button', { name: T.meInstall }));
    expect(event.prompt).toHaveBeenCalledOnce();
  });

  it('shows the share-sheet steps on an iPhone', async () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)'
    );
    list(<InstallLink className="quiet" />);
    const button = await screen.findByRole('button', { name: T.meInstall });
    expect(button).toHaveAttribute('aria-haspopup', 'dialog');
    await userEvent.click(button);
    expect(screen.getByRole('dialog', { name: T.iosTitle })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: T.gotIt }));
    expect(screen.queryByRole('dialog', { name: T.iosTitle })).toBeNull();
  });

  it('is absent in the installed app', () => {
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    const { container } = list(<InstallLink className="quiet" />);
    expect(container.querySelector('li')).toBeNull();
    Reflect.deleteProperty(navigator, 'standalone');
  });
});
