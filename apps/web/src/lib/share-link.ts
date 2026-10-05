import { messages } from '@/messages';

const T = messages.sharing;

export interface Said {
  tone: 'success' | 'info';
  text: string;
}

/**
 * Shares an address: the system's share dialog where the browser has one (a
 * phone: WhatsApp, Telegram, mail...), else the clipboard. Says what happened,
 * or nothing when the system dialog took over or the reader closed it.
 */
export async function shareLink(title: string, url: string): Promise<Said | null> {
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({ title, url });
      return null;
    } catch (error) {
      // Closing the system's share dialog is a choice, not a failure.
      if (error instanceof DOMException && error.name === 'AbortError') {
        return null;
      }
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    return { tone: 'success', text: T.copied };
  } catch {
    return { tone: 'info', text: T.copyFailed };
  }
}
