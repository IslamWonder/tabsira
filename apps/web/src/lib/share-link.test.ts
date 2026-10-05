import { afterEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { shareLink } from './share-link';

const T = messages.sharing;
const URL_ = 'https://tabsira.me/u/reader';

afterEach(() => {
  Reflect.deleteProperty(navigator, 'share');
  vi.restoreAllMocks();
});

function clipboard(write: () => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn(write) },
    configurable: true,
  });
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
}

describe('shareLink', () => {
  it('hands the address to the system dialog and says nothing more', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    expect(await shareLink('t', URL_)).toBeNull();
    expect(share).toHaveBeenCalledWith({ title: 't', url: URL_ });
  });

  it('takes a closed dialog as a choice, and a failed one as a reason to copy', async () => {
    const write = clipboard(async () => undefined);
    const share = vi.fn().mockRejectedValueOnce(new DOMException('closed', 'AbortError'));
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    expect(await shareLink('t', URL_)).toBeNull();
    expect(write).not.toHaveBeenCalled();
    share.mockRejectedValueOnce(new DOMException('no', 'NotAllowedError'));
    expect(await shareLink('t', URL_)).toEqual({ tone: 'success', text: T.copied });
    expect(write).toHaveBeenCalledWith(URL_);
  });

  it('copies where there is no dialog, and says when even that fails', async () => {
    clipboard(async () => undefined);
    expect(await shareLink('t', URL_)).toEqual({ tone: 'success', text: T.copied });
    clipboard(async () => {
      throw new Error('denied');
    });
    expect(await shareLink('t', URL_)).toEqual({ tone: 'info', text: T.copyFailed });
  });
});
