'use client';

import Image from 'next/image';
import { useEffect, useState } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { OrnamentDivider } from '@/components/fx/ornament-divider';
import { ScenePhoto, type ScenePoint } from '@/components/insight/scene-photo';
import { StageLayout } from '@/components/layout/layouts';
import { Chip } from '@/components/ui/chip';
import { Sheet } from '@/components/ui/sheet';
import { messages } from '@/messages';
import { SceneInsightList } from './scene-insight-list';
import { SceneIntro } from './scene-intro';
import { SceneStarter } from './scene-starter';

const EXAMPLE = messages.scene.example;
export const RAIN_PHOTO = { src: '/scene/rain-olive.jpg', width: 768, height: 1344 } as const;

// Where the two insights sit on the rain photo, as ratios of the photo: the
// drops on the large leaf, and the young stem that will outlive its planter.
// Both stay inside the crop of a landscape stage, a phone and a tablet.
const POSITIONS = [
  { x: 0.24, y: 0.555, tone: 'gold' },
  { x: 0.5, y: 0.66, tone: 'emerald' },
] as const;

export const RAIN_POINTS: readonly ScenePoint[] = EXAMPLE.insights.map((insight, index) => ({
  ...insight,
  ...(POSITIONS[index] as (typeof POSITIONS)[number]),
}));

type Received = { kind: 'photo'; url: string; name: string } | { kind: 'link'; url: string };

/**
 * The scene (S01): the prepared rain photo as the stage with its two
 * insights, the panel of the desktop reference beside it, the phone mockup's
 * overlays below 768 px. Until the API serves the curated scene, opening an
 * insight says what will appear there instead of showing anything unverified,
 * and a photo you bring stays on your device: nothing imitates an analysis.
 */
export function SceneExperience() {
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [starterOpen, setStarterOpen] = useState(false);
  const [received, setReceived] = useState<Received | null>(null);
  const point = RAIN_POINTS.find((candidate) => candidate.id === selected);

  // A chosen photo is shown from memory; release it once it is replaced or closed.
  useEffect(() => {
    return () => {
      if (received?.kind === 'photo') {
        URL.revokeObjectURL(received.url);
      }
    };
  }, [received]);

  const takeFile = (file: File) => {
    setStarterOpen(false);
    setReceived({ kind: 'photo', url: URL.createObjectURL(file), name: file.name });
  };
  const takeLink = (url: string) => {
    setStarterOpen(false);
    setReceived({ kind: 'link', url });
  };

  return (
    <>
      <StageLayout
        stageLabel={EXAMPLE.alt}
        panel={
          <div className="hidden flex-col gap-7 pt-2 pb-6 tablet:flex">
            <SceneIntro chip={<Chip>{messages.scene.prepared}</Chip>} />
            <SceneInsightList points={RAIN_POINTS} selectedId={selected} onSelect={setSelected} />
            <OrnamentDivider />
            <SceneStarter onFile={takeFile} onLink={takeLink} />
          </div>
        }
        stage={
          <ScenePhoto
            src={RAIN_PHOTO.src}
            alt={EXAMPLE.alt}
            width={RAIN_PHOTO.width}
            height={RAIN_PHOTO.height}
            points={RAIN_POINTS}
            selectedId={selected}
            onSelect={setSelected}
            listInPanel
            priority
            className="h-full"
          >
            {/* The phone mockup: the name and the state on top, the hint and the way to a new scene below. */}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-5 pt-[max(20px,env(safe-area-inset-top))] tablet:hidden">
              <h1 className="m-0">
                <LogoMark title={messages.brand.name} className="h-14" />
              </h1>
              <Chip tone="glass">{messages.scene.prepared}</Chip>
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
        open={point !== undefined}
        onClose={() => setSelected(undefined)}
        title={point?.title ?? ''}
        description={point?.glimpse}
      >
        <div className="flex flex-col items-start gap-3 pb-2">
          <Chip tone="primary">{messages.comingSoon.badge}</Chip>
          <p className="m-0 text-fg leading-[1.9]">{EXAMPLE.opening}</p>
          <p className="m-0 text-fg-muted text-sm">{EXAMPLE.pending}</p>
        </div>
      </Sheet>

      <Sheet
        open={starterOpen}
        onClose={() => setStarterOpen(false)}
        title={messages.nav.captureScene}
      >
        <SceneStarter onFile={takeFile} onLink={takeLink} className="mb-2" />
      </Sheet>

      <Sheet
        open={received !== null}
        onClose={() => setReceived(null)}
        title={
          received?.kind === 'link'
            ? messages.scene.received.linkTitle
            : messages.scene.received.photoTitle
        }
      >
        <div className="flex flex-col gap-4 pb-2">
          {received?.kind === 'photo' ? (
            <div className="relative h-64 overflow-hidden rounded-[var(--radius-panel)]">
              <Image
                src={received.url}
                alt={messages.scene.received.photoAlt}
                fill
                unoptimized
                className="object-contain"
              />
            </div>
          ) : (
            <p
              dir="ltr"
              className="m-0 break-all rounded-[var(--radius-card)] bg-surface px-3 py-2 text-fg-soft text-sm"
            >
              {received?.url}
            </p>
          )}
          <p className="m-0 text-fg-soft leading-[1.9]">{messages.scene.received.note}</p>
        </div>
      </Sheet>
    </>
  );
}
