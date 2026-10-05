'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { ShieldIcon } from '@/components/icons';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';
import { useProgress } from '@/progress/use-progress';
import { BadgeGrid } from './badge-grid';
import { MeaningSkyScene } from './meaning-sky';
import { QuestCard } from './quest-card';
import { RankCard } from './rank-card';
import { StreakCard } from './streak-card';

const M = messages.practiceView;

const COUNTS = [
  ['looks', 'looks'],
  ['completed', 'completed'],
  ['actions_done', 'actionsDone'],
  ['places', 'places'],
  ['treasures', 'treasures'],
  ['questions', 'questions'],
] as const;

function Counts({ counts }: { counts: Progress['counts'] }) {
  return (
    <GlassPanel as="section" aria-labelledby="practice-counts" className="flex flex-col gap-3">
      <h2 id="practice-counts" className="m-0 font-bold font-display text-heading text-fg">
        {M.counts.title}
      </h2>
      <dl className="m-0 grid grid-cols-2 gap-2 tablet:grid-cols-3">
        {COUNTS.map(([field, label]) => (
          <div
            key={field}
            className="flex flex-col gap-0.5 rounded-[var(--radius-card)] border border-line p-3"
          >
            <dd className="m-0 font-bold font-display text-heading text-fg">{counts[field]}</dd>
            <dt className="text-fg-muted text-sm">{M.counts[label]}</dt>
          </div>
        ))}
      </dl>
    </GlassPanel>
  );
}

function Disclaimer({ text }: { text: string }) {
  return (
    <p className="m-0 flex items-start gap-2 text-fg-muted text-sm leading-[1.8]">
      <ShieldIcon width="18" height="18" className="mt-1 shrink-0 text-[var(--ornament)]" />
      {text}
    </p>
  );
}

/** The page's name and the way back, small at the top of the scene: the scene's own heading leads. */
function Trail() {
  return (
    <div className="sky-text-shadow flex items-center gap-2 text-[14px]">
      <Link
        href="/me"
        className="inline-flex min-h-11 items-center text-[var(--sky-gold)] underline-offset-4 hover:underline"
      >
        {M.back}
      </Link>
      <span aria-hidden="true" className="text-[var(--sky-gold)]">
        ‹
      </span>
      <h1 className="m-0 font-semibold text-[14px] text-[var(--sky-text)]">{M.title}</h1>
    </div>
  );
}

/** The page frame: the scene at full width under the top bar, then the page's own column. Shared with the gallery. */
export function ProgressFrame({ children }: { children: ReactNode }) {
  return <div className="flex w-full flex-col pb-6 tablet:pb-8">{children}</div>;
}

/** Everything under the scene: the lead, then the practice that is not the sky. */
function ProgressBody({ children }: { children?: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 pt-6 tablet:px-6 tablet:pt-8 desktop:px-10">
      <p className="m-0 max-w-[40rem] text-fg-soft leading-[1.9]">{M.lead}</p>
      {children}
    </div>
  );
}

export function ProgressView({
  progress,
  refreshing = false,
}: {
  progress: Progress;
  refreshing?: boolean;
}) {
  return (
    <>
      <MeaningSkyScene
        state={{ status: 'ready', sky: progress.sky, refreshing }}
        trail={<Trail />}
      />
      <ProgressBody>
        <div className="grid grid-cols-1 gap-4 *:min-w-0 tablet:grid-cols-2 desktop:grid-cols-3 desktop:gap-6">
          <RankCard rank={progress.rank} />
          <StreakCard streak={progress.streak} />
          <QuestCard quest={progress.daily_quest} />
        </div>
        <div className="grid grid-cols-1 gap-4 *:min-w-0 desktop:grid-cols-2 desktop:items-start desktop:gap-6">
          <BadgeGrid badges={progress.badges} />
          <Counts counts={progress.counts} />
        </div>
        <Disclaimer text={progress.disclaimer} />
      </ProgressBody>
    </>
  );
}

/**
 * The practice screen: the sky of meanings first, then practice ranks, the
 * streak, the daily quest and the badges, from what the learner's own recorded
 * actions add up to. The framing is practice, never piety: no comparison with
 * anyone, no leaderboard, no score of faith, and the API's disclaimer closes
 * the page (decision 27). Until the record arrives, or if it cannot, the scene
 * says so itself; a failure is never drawn as an empty sky.
 */
export function ProgressScreen() {
  const { load, reload } = useProgress();
  return (
    <ProgressFrame>
      {load.status === 'ready' ? (
        <ProgressView progress={load.progress} refreshing={load.refreshing} />
      ) : (
        <>
          <MeaningSkyScene
            state={
              load.status === 'failed' ? { status: 'failed', retry: reload } : { status: 'loading' }
            }
            trail={<Trail />}
          />
          <ProgressBody />
        </>
      )}
    </ProgressFrame>
  );
}
