import { vi } from 'vitest';
import type { BeforeInstallPromptEvent } from '@/pwa/install';

/** A browser's install prompt whose dialog answers `outcome`. */
export function installPrompt(outcome: 'accepted' | 'dismissed' = 'accepted') {
  const event = new Event('beforeinstallprompt') as BeforeInstallPromptEvent;
  Object.assign(event, {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome }),
  });
  return event;
}
