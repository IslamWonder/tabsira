'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { DownloadIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/sheet';
import { messages } from '@/messages';
import {
  dismissOffer,
  listenForInstall,
  markEngaged,
  mayOffer,
  noteVisit,
  promptInstall,
} from '@/pwa/install';
import { ENGAGED_EVENT, useInstall } from '@/pwa/use-install';

const T = messages.install;
/** Leaves the completion's own moment (its banner and burst) to finish first. */
export const OFFER_DELAY_MS = 2500;
/** Time on the site, in one visit, that shows interest. */
export const ENGAGE_AFTER_MS = 40_000;
/** Pages opened in one visit that show interest. */
export const ENGAGE_PAGES = 3;

/** The reader showed interest: kept for later visits, and told to the offer at once. */
function engage() {
  markEngaged();
  window.dispatchEvent(new Event(ENGAGED_EVENT));
}

/** The two taps of Safari's share sheet, the only way to install on an iPhone or iPad. */
export function IosSteps({ open, onClose }: Readonly<{ open: boolean; onClose: () => void }>) {
  return (
    <Sheet open={open} onClose={onClose} title={T.iosTitle}>
      <ol className="m-0 flex list-decimal flex-col gap-3 ps-6 pb-2 text-fg leading-[1.9]">
        {T.iosSteps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <div className="pt-3 pb-2">
        <Button onClick={onClose}>{T.gotIt}</Button>
      </div>
    </Sheet>
  );
}

/**
 * The offer to install, as a quiet card above the phone's navigation: never in
 * the first moments of a first visit, only once the reader showed interest (see
 * src/pwa/install.ts), never on the analysis it would cover, never again for a
 * while after install.later, and never in the installed app. It is not modal:
 * the page stays usable under it.
 */
export function InstallOffer() {
  const install = useInstall();
  const [due, setDue] = useState(false);
  const [iosOpen, setIosOpen] = useState(false);

  const pathname = usePathname();
  const pages = useRef(new Set<string>());

  useEffect(() => {
    listenForInstall();
    noteVisit();
    const timer = setTimeout(engage, ENGAGE_AFTER_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    pages.current.add(pathname);
    if (pages.current.size === ENGAGE_PAGES) {
      engage();
    }
  }, [pathname]);

  useEffect(() => {
    if (mayOffer(install)) {
      setDue(true);
      return;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const engaged = () => {
      timer = setTimeout(() => setDue(mayOffer(install)), OFFER_DELAY_MS);
    };
    window.addEventListener(ENGAGED_EVENT, engaged);
    return () => {
      window.removeEventListener(ENGAGED_EVENT, engaged);
      clearTimeout(timer);
    };
  }, [install]);

  const later = () => {
    dismissOffer();
    setDue(false);
  };

  const accept = async () => {
    if (install.way === 'ios') {
      setIosOpen(true);
      return;
    }
    await promptInstall();
    setDue(false);
  };

  const visible =
    due && !install.installed && install.way !== 'none' && !pathname.startsWith('/scan/');

  return (
    <>
      {visible ? (
        <section
          aria-label={T.region}
          className="glass fixed inset-x-4 bottom-[calc(var(--nav-clearance)-8px)] z-40 mx-auto max-w-md rounded-[20px] p-4 shadow-[var(--panel-shadow)] motion-safe:animate-rise tablet:inset-x-auto tablet:end-6 tablet:bottom-6"
        >
          <div className="flex items-start gap-3">
            {/* biome-ignore lint/performance/noImgElement: the app's own icon, a fixed small file; next/image adds nothing here. */}
            <img
              src="/icons/icon-192.png"
              alt=""
              width={48}
              height={48}
              className="size-12 shrink-0 rounded-[12px]"
            />
            <div className="min-w-0 flex-1">
              <h2 className="m-0 font-bold text-[1.0625rem] text-fg">{T.title}</h2>
              <p className="m-0 mt-1 text-fg-soft text-sm leading-[1.8]">{T.body}</p>
            </div>
          </div>
          <div className="mt-3 flex gap-2.5">
            <Button onClick={() => void accept()}>
              <DownloadIcon aria-hidden="true" className="size-5" />
              {install.way === 'ios' ? T.iosShow : T.install}
            </Button>
            <Button variant="ghost" onClick={later}>
              {T.later}
            </Button>
          </div>
        </section>
      ) : null}
      <IosSteps
        open={iosOpen}
        onClose={() => {
          setIosOpen(false);
          later();
        }}
      />
    </>
  );
}
