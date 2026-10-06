'use client';

import { useEffect, useState } from 'react';
import { DownloadIcon } from '@/components/icons';
import { messages } from '@/messages';
import { listenForInstall, promptInstall } from '@/pwa/install';
import { useInstall } from '@/pwa/use-install';
import { IosSteps } from './install-offer';

const T = messages.install;

/**
 * The footer's way to install, on every page and from the first visit, the
 * way web apps keep an «install» entry in reach: a quiet link-like button that
 * opens the browser's dialog, or the share-sheet steps on an iPhone. Shown only
 * where the browser can install, and never in the installed app.
 */
export function InstallLink({ className }: Readonly<{ className: string }>) {
  const install = useInstall();
  const [iosOpen, setIosOpen] = useState(false);

  useEffect(() => {
    listenForInstall();
  }, []);

  if (install.installed || install.way === 'none') {
    return null;
  }
  const run = () => {
    if (install.way === 'ios') {
      setIosOpen(true);
      return;
    }
    void promptInstall();
  };
  return (
    <li>
      <button
        type="button"
        onClick={run}
        aria-haspopup={install.way === 'ios' ? 'dialog' : undefined}
        className={className}
      >
        <DownloadIcon aria-hidden="true" className="me-2 size-5" />
        {T.meInstall}
      </button>
      <IosSteps open={iosOpen} onClose={() => setIosOpen(false)} />
    </li>
  );
}
