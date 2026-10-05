'use client';

import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { useCapture } from '@/components/capture/capture-provider';
import { SparkIcon } from '@/components/icons';
import { ScenePhoto, type ScenePoint } from '@/components/insight/scene-photo';
import { StageLayout } from '@/components/layout/layouts';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { getRainTutorial, keepRainInsight, type Tutorial } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { centre } from '@/lib/scan/spans';
import { messages } from '@/messages';
import { CaptureCard } from './capture-card';
import { RAIN_PHOTO } from './rain-scene';
import { SceneInsightList } from './scene-insight-list';
import { SceneIntro } from './scene-intro';

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

/**
 * The scene (S01): the prepared rain photo first, before any account or
 * permission, labelled as the prepared example the API says it is; its two
 * insights open the API's own copy of them. A photo or the camera (the
 * layout's CaptureProvider) starts a real scan, which is the only thing that is ever called analysis:
 * the prepared example is never presented as one. The first paint never waits
 * for the API: the photo and the insights' names are here already, and the
 * API's own titles and places replace them when they arrive.
 */
export function SceneExperience() {
  const router = useRouter();
  const capture = useCapture();
  const [tutorial, setTutorial] = useState<Tutorial | null>(null);
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

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

  return (
    <StageLayout
      stageFirstOnPhone
      stageLabel={alt}
      // On a phone the photo leaves room for the invitation under it: the example and the
      // reader's own scene share the first screen, and the page scrolls only to the footer.
      stageClassName="h-[min(62svh,600px)] min-h-[340px]"
      panel={
        <div className="relative z-10 -mt-14 flex flex-col gap-6 px-4 pb-6 tablet:mt-0 tablet:gap-7 tablet:px-0 tablet:pt-2">
          {/* On a phone the title is for screen readers; the photo and its state say it to the eye. */}
          <div className="sr-only tablet:not-sr-only">
            <SceneIntro chip={<Chip>{label}</Chip>} />
          </div>
          <div className="hidden tablet:block">
            <SceneInsightList points={points} selectedId={selected} onSelect={open} />
          </div>
          <CaptureCard onCamera={capture.open} onFile={capture.send} />
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
          {/* The phone mockup: the name and the state on top, the hint above the invitation. */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 top-0 flex items-center justify-between px-4 pt-[max(16px,env(safe-area-inset-top))] tablet:hidden"
          >
            <LogoMark className="h-12" />
            <Chip tone="glass">{label}</Chip>
          </div>
          <div className="absolute inset-x-4 top-20 z-20 flex flex-col items-center gap-2 tablet:top-6">
            <div role="status">
              {opening === null ? null : <Notice tone="info">{messages.sending.opening}</Notice>}
            </div>
            {openError === null ? null : (
              <div role="alert">
                <Notice tone="error">{openError}</Notice>
              </div>
            )}
          </div>
          {/* The photo melts into the page where the invitation rises from it. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-[linear-gradient(to_top,var(--stage-fade)_15%,transparent)] tablet:hidden"
          />
          <p className="absolute inset-x-0 bottom-[4.75rem] m-0 flex items-center justify-center gap-2 px-4 text-center font-semibold text-fg text-lg tablet:hidden">
            <SparkIcon width="18" height="18" className="text-[var(--glow-gold)]" />
            {messages.scene.hint}
          </p>
        </ScenePhoto>
      }
    />
  );
}
