'use client';

import { useEffect, useState } from 'react';
import { IosSteps } from '@/components/app/install-offer';
import { DownloadIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';
import { listenForInstall, promptInstall } from '@/pwa/install';
import { useInstall } from '@/pwa/use-install';
import { MeSection } from './me-section';

const T = messages.install;

/**
 * The app section of the profile page: the install button always within reach, whatever the
 * offer card was told. In the installed app it says so; where the browser
 * cannot install (a desktop Firefox) it is a single line.
 */
export function AppSection() {
  const install = useInstall();
  const [iosOpen, setIosOpen] = useState(false);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    listenForInstall();
  }, []);

  const run = async () => {
    if (install.way === 'ios') {
      setIosOpen(true);
      return;
    }
    setAccepted(await promptInstall());
  };

  return (
    <MeSection id="app" title={messages.pages.me.sections.app}>
      <div role="status">{accepted ? <Notice tone="success">{T.accepted}</Notice> : null}</div>
      {install.installed && !accepted ? (
        <p className="m-0 text-fg-soft leading-[1.8]">{T.meInstalled}</p>
      ) : null}
      {!install.installed && install.way !== 'none' ? (
        <div className="flex flex-col items-start gap-3">
          <p className="m-0 text-fg-soft leading-[1.8]">{T.meHint}</p>
          <Button onClick={() => void run()}>
            <DownloadIcon aria-hidden="true" className="size-5" />
            {T.meInstall}
          </Button>
        </div>
      ) : null}
      {!install.installed && install.way === 'none' ? (
        <p className="m-0 text-fg-soft leading-[1.8]">{T.meUnsupported}</p>
      ) : null}
      <IosSteps open={iosOpen} onClose={() => setIosOpen(false)} />
    </MeSection>
  );
}
