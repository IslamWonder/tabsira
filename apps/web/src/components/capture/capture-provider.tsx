'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { markProfileRequired, tutorialOffered, useSession } from '@/account/session';
import { SummoningCircle } from '@/components/fx/summoning-circle';
import { OnwardArrowIcon } from '@/components/icons';
import { SceneStarter } from '@/components/scene/scene-starter';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { startScanFromFile } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { accountRequired, profileRequired, signUpHref } from '@/lib/scan/gate';
import { messages } from '@/messages';

export interface Capture {
  /** Open the capture sheet; its live camera starts at once, the reader's tap being the gesture. */
  open: () => void;
  /** Send a photo the reader took or chose to a new scan, then go to that scan. */
  send: (file: File) => void;
}

const CaptureContext = createContext<Capture | null>(null);

/**
 * One way to capture a scene, from every page (decision 51): each capture button
 * opens this sheet with the live camera already starting and the file picker
 * beside it, and every photo, taken or chosen, is sent the same way. The sheet
 * says what is being sent without the file's name, and a refusal is said in
 * Arabic with a way to try again; nothing is shown back of the photo.
 */
export function CaptureProvider({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useSession();
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState<File | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  const send = useCallback(
    async (file: File) => {
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      setOpen(false);
      setSending(file);
      setFailure(null);
      const result = await startScanFromFile(file, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      if (result.ok) {
        setSending(null);
        router.push(`/scan/${result.data.id}` as Route);
        return;
      }
      if (accountRequired(result)) {
        // The guest's one own scan is used: sign up, then come back to where they were (decision 64).
        setSending(null);
        router.push(signUpHref(pathname, 'scan'));
        return;
      }
      if (profileRequired(result)) {
        // The profile form opens before anything else; the photo is sent again once it is complete.
        markProfileRequired();
      }
      setFailure(journeyFailureMessage(result));
    },
    [router, pathname]
  );

  const leave = () => {
    request.current?.abort();
    setSending(null);
    setFailure(null);
  };

  // The installed app's capture shortcut opens on /?capture=1: the reader's own long-press is the tap that asks.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get('capture') !== '1') {
      return;
    }
    url.searchParams.delete('capture');
    window.history.replaceState(
      window.history.state,
      '',
      `${url.pathname}${url.search}${url.hash}`
    );
    setOpen(true);
  }, []);

  const capture = useMemo<Capture>(
    () => ({ open: () => setOpen(true), send: (file) => void send(file) }),
    [send]
  );

  return (
    <CaptureContext.Provider value={capture}>
      {children}
      <Sheet open={open} onClose={() => setOpen(false)} title={messages.nav.captureScene}>
        <SceneStarter onFile={capture.send} startCamera className="mb-2" />
        {/* The third way in: the prepared example, with no camera and no photo. */}
        {tutorialOffered(session) ? (
          <Link
            href={'/#example' as Route}
            onClick={() => setOpen(false)}
            className="mb-2 inline-flex min-h-12 items-center gap-2 font-semibold text-link underline-offset-4 hover:underline"
          >
            {messages.landing.hero.tryExample}
            <OnwardArrowIcon width="18" height="18" />
          </Link>
        ) : null}
      </Sheet>
      <Sheet open={sending !== null} onClose={leave} title={messages.sending.title}>
        <div className="flex flex-col gap-4 pb-2">
          {/* No photo is shown back (a sensitive scene never is): the circle turns while it travels. */}
          {failure === null ? (
            <div className="flex justify-center pt-1">
              <SummoningCircle active size={112} />
            </div>
          ) : null}
          <p role="status" className="m-0 text-center text-fg leading-[1.9] empty:hidden">
            {failure === null ? messages.sending.file : null}
          </p>
          {failure === null ? null : (
            <div role="alert">
              <Notice tone="error">{failure}</Notice>
            </div>
          )}
          <p className="m-0 text-fg-muted text-sm leading-[1.8]">{messages.sending.privacy}</p>
          <div className="flex flex-wrap gap-2.5">
            {failure === null || sending === null ? null : (
              <Button onClick={() => void send(sending)}>{messages.sending.retry}</Button>
            )}
            <Button variant="ghost" onClick={leave}>
              {failure === null ? messages.sending.cancel : messages.sending.close}
            </Button>
          </div>
        </div>
      </Sheet>
    </CaptureContext.Provider>
  );
}

/** The capture of the page; every page is inside a CaptureProvider (the root layout's). */
export function useCapture(): Capture {
  const capture = useContext(CaptureContext);
  if (capture === null) {
    throw new Error('useCapture is used outside a CaptureProvider');
  }
  return capture;
}
