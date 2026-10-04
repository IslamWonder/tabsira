'use client';

import { useEffect } from 'react';

/**
 * Registers public/sw.js in production builds only: in development a cached
 * shell would hide the change being worked on.
 */
export function ServiceWorkerRegister({
  enabled = process.env.NODE_ENV === 'production',
}: {
  enabled?: boolean;
}) {
  useEffect(() => {
    if (!enabled || !('serviceWorker' in navigator)) {
      return;
    }
    navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(() => {
      // The app works without it; only the offline page is lost.
    });
  }, [enabled]);
  return null;
}
