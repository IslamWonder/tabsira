'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { messages } from '@/messages';

/**
 * Registers public/sw.js in production builds only: in development a cached
 * shell would hide the change being worked on.
 *
 * The worker takes over as soon as a new release is installed. A page already
 * open keeps the code it loaded, so it says a new version is ready and offers
 * the reload instead of reloading under the reader's hands. The first worker
 * of a visit (no controller before it) is not an update and says nothing.
 */
export function ServiceWorkerRegister({
  enabled = process.env.NODE_ENV === 'production',
}: Readonly<{
  enabled?: boolean;
}>) {
  const [updated, setUpdated] = useState(false);

  useEffect(() => {
    if (!enabled || !('serviceWorker' in navigator)) {
      return;
    }
    const container = navigator.serviceWorker;
    let hadController = container.controller !== null;
    const onChange = () => {
      if (hadController) {
        setUpdated(true);
      }
      hadController = true;
    };
    container.addEventListener('controllerchange', onChange);
    container.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(() => {
      // The app works without it; only the offline page is lost.
    });
    return () => container.removeEventListener('controllerchange', onChange);
  }, [enabled]);

  if (!updated) {
    return null;
  }
  return (
    <div
      role="status"
      className="glass fixed inset-x-4 top-[calc(var(--topbar-height)+8px)] z-50 mx-auto flex max-w-md items-center justify-between gap-3 rounded-[16px] px-4 py-3 shadow-[var(--panel-shadow)] motion-safe:animate-fade-in"
    >
      <span className="text-[0.9375rem] text-fg">{messages.install.updateReady}</span>
      <Button onClick={() => window.location.reload()}>{messages.install.updateNow}</Button>
    </div>
  );
}
