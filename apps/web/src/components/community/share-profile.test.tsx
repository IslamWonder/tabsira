import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { ShareProfile } from './share-profile';

const P = messages.community.profile;

afterEach(() => {
  Reflect.deleteProperty(navigator, 'share');
});

describe('ShareProfile', () => {
  it('shares the owner’s public page with its name, and copies it where there is no dialog', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    const { unmount } = render(<ShareProfile handle="reader" label="[قارئ]" own />);
    await userEvent.click(screen.getByRole('button', { name: P.shareOwn }));
    expect(share).toHaveBeenCalledWith({
      title: P.shareTitle('[قارئ]'),
      url: expect.stringMatching(/\/u\/reader$/),
    });
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
    unmount();

    Reflect.deleteProperty(navigator, 'share');
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    render(<ShareProfile handle="other" label="@other" own={false} variant="ghost" />);
    await userEvent.click(screen.getByRole('button', { name: P.shareOther }));
    expect(screen.getByRole('status')).toHaveTextContent(messages.sharing.copied);
  });
});
