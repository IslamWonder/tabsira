'use client';

import type { ReactNode } from 'react';
import { PageContainer } from '@/components/layout/layouts';
import { ProgressFrame, ProgressView } from '@/components/progress/progress-screen';
import { WorldView } from '@/components/world/world-screen';
import { messages } from '@/messages';
import { PROGRESS, PROGRESS_EMPTY, WORLD, WORLD_UNDER_FOG } from '@/test/world';
import { type Viewport, ViewportPreview } from '../ui/viewport-preview';

const D = messages.devWorld;
const THEMES = ['light', 'dark'] as const;

interface Frame {
  key: string;
  label: string;
  viewport: Viewport;
  height: number;
  node: ReactNode;
}

const noop = () => undefined;

/** The states of the world and practice screens on sample data, for review at 375 and 1440 px. */
const FRAMES: readonly Frame[] = [
  ...(['phone', 'desktop'] as const).flatMap((viewport) => {
    const height = viewport === 'phone' ? 1700 : 900;
    return [
      {
        key: `world-${viewport}`,
        label: D.states.world,
        viewport,
        height,
        node: <WorldView world={WORLD} onVisited={noop} />,
      },
      {
        key: `opened-${viewport}`,
        label: D.states.opened,
        viewport,
        height,
        node: <WorldView world={WORLD} onVisited={noop} initialSelected="T01" />,
      },
      {
        key: `newcomer-${viewport}`,
        label: D.states.newcomer,
        viewport,
        height,
        node: <WorldView world={WORLD_UNDER_FOG} onVisited={noop} />,
      },
      {
        key: `practice-${viewport}`,
        label: D.states.practice,
        viewport,
        height: viewport === 'phone' ? 2700 : 1500,
        node: (
          <ProgressFrame>
            <ProgressView progress={PROGRESS} />
          </ProgressFrame>
        ),
      },
      {
        key: `practice-empty-${viewport}`,
        label: D.states.practiceEmpty,
        viewport,
        height: viewport === 'phone' ? 2700 : 1500,
        node: (
          <ProgressFrame>
            <ProgressView progress={PROGRESS_EMPTY} />
          </ProgressFrame>
        ),
      },
    ];
  }),
];

export function WorldGallery() {
  return (
    <PageContainer className="flex flex-col gap-10 pt-[max(28px,env(safe-area-inset-top))] pb-12">
      <header className="flex flex-col gap-1">
        <h1 className="m-0 font-bold font-display text-3xl text-fg">{D.title}</h1>
        <p className="m-0 text-fg-soft">{D.description}</p>
      </header>
      {THEMES.map((theme) => (
        <section
          key={theme}
          aria-label={messages.dev.themes[theme]}
          className="flex flex-col gap-6"
        >
          <h2 className="m-0 font-bold font-display text-2xl text-fg">
            {messages.dev.themes[theme]}
          </h2>
          {FRAMES.map((frame) => (
            <ViewportPreview
              key={frame.key}
              viewport={frame.viewport}
              theme={theme}
              height={frame.height}
              label={`${frame.label} · ${messages.dev.viewports[frame.viewport]}`}
            >
              {frame.node}
            </ViewportPreview>
          ))}
        </section>
      ))}
    </PageContainer>
  );
}
