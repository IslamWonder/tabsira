'use client';

import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { OrnamentDivider } from '@/components/fx/ornament-divider';
import { ScenePhoto, type ScenePoint } from '@/components/insight/scene-photo';
import { StageLayout } from '@/components/layout/layouts';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { getRainTutorial, keepRainInsight, startScanFromFile, type Tutorial } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { centre } from '@/lib/scan/spans';
import { messages } from '@/messages';
import { RAIN_PHOTO } from './rain-scene';
import { SceneInsightList } from './scene-insight-list';
import { SceneIntro } from './scene-intro';
import { SceneStarter } from './scene-starter';

export { RAIN_PHOTO };

const EXAMPLE = messages.scene.example;

// Where the two insights sit on the rain photo until the API's own anchors
// arrive, as ratios of the photo. Both stay inside the crop of a landscape
// stage, a phone and a tablet. The ids are the tutorial's own slugs.
const POSITIONS = [
  { x: 0.24, y: 0.555, tone: 'gold' },
  { x: 0.5, y: 0.66, tone: 'emerald' },
] as const;

export const RAIN_POINTS: readonly ScenePoint[] = EXAMPLE.insights.map((insight, index) => ({
  ...insight,
  ...(POSITIONS[index] as (typeof POSITIONS)[number]),
}));

/** The tutorial's insights as points of the photo, in the API's titles and anchors. */
function pointsOf(tutorial: Tutorial): ScenePoint[] {
  return tutorial.insights.map((insight, index) => ({
    id: insight.slug,
    ...centre(insight.anchor),
    title: insight.title,
    glimpse: insight.glimpse,
    tone: index % 2 === 0 ? 'gold' : 'emerald',
  }));
}

type Sending = { kind: 'file'; file: File };

/**
 * The scene (S01): the prepared rain photo first, before any account or
 * permission, labelled as the prepared example the API says it is; its two
 * insights open the API's own copy of them. A photo or the camera
 * starts a real scan, which is the only thing that is ever called analysis:
 * the prepared example is never presented as one. The first paint never waits
 * for the API: the photo and the insights' names are here already, and the
 * API's own titles and places replace them when they arrive.
 */
export function SceneExperience() {
  const router = useRouter();
  const [tutorial, setTutorial] = useState<Tutorial | null>(null);
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const [starterOpen, setStarterOpen] = useState(false);
  const [sending, setSending] = useState<Sending | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getRainTutorial(controller.signal).then((result) => {
      if (result.ok && !controller.signal.aborted) {
        setTutorial(result.data);
      }
    });
    return () => controller.abort();
  }, []);

  const points = tutorial === null ? RAIN_POINTS : pointsOf(tutorial);
  const label = tutorial?.label ?? messages.scene.prepared;
  const alt = tutorial?.image.alt ?? EXAMPLE.alt;

  const open = async (slug: string) => {
    if (opening !== null) {
      return;
    }
    setSelected(slug);
    setOpening(slug);
    setOpenError(null);
    const result = await keepRainInsight(slug);
    if (result.ok) {
      router.push(`/insight/${result.data.id}` as Route);
      return;
    }
    setOpening(null);
    setOpenError(journeyFailureMessage(result));
  };

  const send = async (input: Sending) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setStarterOpen(false);
    setSending(input);
    setSendError(null);
    const result = await startScanFromFile(input.file, controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    if (result.ok) {
      router.push(`/scan/${result.data.id}` as Route);
      return;
    }
    setSendError(journeyFailureMessage(result));
  };

  const leaveSending = () => {
    request.current?.abort();
    setSending(null);
    setSendError(null);
  };

  const takeFile = (file: File) => void send({ kind: 'file', file });

  return (
    <>
      <StageLayout
        stageLabel={alt}
        panel={
          <div className="hidden flex-col gap-7 pt-2 pb-6 tablet:flex">
            <SceneIntro chip={<Chip>{label}</Chip>} />
            <SceneInsightList points={points} selectedId={selected} onSelect={open} />
            <OrnamentDivider />
            <SceneStarter onFile={takeFile} />
          </div>
        }
        stage={
          <ScenePhoto
            src={RAIN_PHOTO.src}
            alt={alt}
            width={RAIN_PHOTO.width}
            height={RAIN_PHOTO.height}
            points={points}
            selectedId={selected}
            onSelect={open}
            listInPanel
            priority
            className="h-full"
          >
            {/* The phone mockup: the name and the state on top, the hint and the way to a new scene below. */}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-5 pt-[max(20px,env(safe-area-inset-top))] tablet:hidden">
              <div className="m-0">
                <LogoMark title={messages.brand.name} className="h-14" />
              </div>
              <Chip tone="glass">{label}</Chip>
            </div>
            <div className="absolute inset-x-4 top-24 z-20 flex flex-col items-center gap-2 tablet:top-6">
              <div role="status">
                {opening === null ? null : <Notice tone="info">{messages.sending.opening}</Notice>}
              </div>
              {openError === null ? null : (
                <div role="alert">
                  <Notice tone="error">{openError}</Notice>
                </div>
              )}
            </div>
            <div className="absolute inset-x-0 bottom-[calc(var(--nav-clearance)+4px)] flex flex-col items-center gap-0.5 px-5 text-center tablet:hidden">
              <p className="m-0 font-semibold text-[1.3rem] text-fg">{messages.scene.hint}</p>
              <button
                type="button"
                onClick={() => setStarterOpen(true)}
                aria-haspopup="dialog"
                className="flex min-h-12 items-center px-3 text-link"
              >
                {messages.scene.captureOwn}
              </button>
            </div>
          </ScenePhoto>
        }
      />

      <Sheet
        open={starterOpen}
        onClose={() => setStarterOpen(false)}
        title={messages.nav.captureScene}
      >
        <SceneStarter onFile={takeFile} className="mb-2" />
      </Sheet>

      <Sheet open={sending !== null} onClose={leaveSending} title={messages.sending.title}>
        <div className="flex flex-col gap-4 pb-2">
          {sending === null ? null : (
            <p role="status" className="m-0 text-fg leading-[1.9]">
              {sendError === null ? messages.sending.file(sending.file.name) : null}
            </p>
          )}
          {sendError === null ? null : (
            <div role="alert">
              <Notice tone="error">{sendError}</Notice>
            </div>
          )}
          <p className="m-0 text-fg-muted text-sm leading-[1.8]">{messages.sending.privacy}</p>
          <div className="flex flex-wrap gap-2.5">
            {sendError === null || sending === null ? null : (
              <Button onClick={() => void send(sending)}>{messages.sending.retry}</Button>
            )}
            <Button variant="ghost" onClick={leaveSending}>
              {sendError === null ? messages.sending.cancel : messages.sending.close}
            </Button>
          </div>
        </div>
      </Sheet>
    </>
  );
}
