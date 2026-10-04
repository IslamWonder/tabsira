'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { ShieldIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';
import { useProgress } from '@/progress/use-progress';
import { BadgeGrid } from './badge-grid';
import { QuestCard } from './quest-card';
import { RankCard } from './rank-card';
import { SkyOfMeanings } from './sky-of-meanings';
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
      <h2 id="practice-counts" className="m-0 font-bold font-display text-[1.5rem] text-fg">
        {M.counts.title}
      </h2>
      <dl className="m-0 grid grid-cols-2 gap-2 tablet:grid-cols-3">
        {COUNTS.map(([field, label]) => (
          <div
            key={field}
            className="flex flex-col gap-0.5 rounded-[var(--radius-card)] border border-line p-3"
          >
            <dd className="m-0 font-bold font-display text-[1.5rem] text-fg">{counts[field]}</dd>
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

function Header() {
  return (
    <header className="flex flex-col gap-1">
      <Link
        href="/me"
        className="inline-flex min-h-12 items-center self-start text-link text-sm underline-offset-4 hover:underline"
      >
        {M.back}
      </Link>
      <h1 className="m-0 font-bold font-display text-[2rem] text-fg">{M.title}</h1>
      <p className="m-0 max-w-[40rem] text-fg-soft leading-[1.9]">{M.lead}</p>
    </header>
  );
}

/** The page frame: its width, the way back and the title. Shared with the gallery's still pictures. */
export function ProgressFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 pt-[max(24px,env(safe-area-inset-top))] pb-6 tablet:px-6 tablet:py-8 desktop:px-10">
      <Header />
      {children}
    </div>
  );
}

export function ProgressView({ progress }: { progress: Progress }) {
  return (
    <>
      <div className="grid gap-4 desktop:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] desktop:items-start desktop:gap-6">
        <div className="flex min-w-0 flex-col gap-4">
          <RankCard rank={progress.rank} />
          <StreakCard streak={progress.streak} />
          <QuestCard quest={progress.daily_quest} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <SkyOfMeanings sky={progress.sky} />
          <BadgeGrid badges={progress.badges} />
          <Counts counts={progress.counts} />
        </div>
      </div>
      <Disclaimer text={progress.disclaimer} />
    </>
  );
}

/**
 * The practice screen: practice ranks, the streak, the daily quest, the sky of meanings
 * and the badges, from what the learner's own recorded actions add up to. The
 * framing is practice, never piety: no comparison with anyone, no leaderboard,
 * no score of faith, and the API's disclaimer closes the page (decision 27).
 */
export function ProgressScreen() {
  const { load, reload } = useProgress();
  return (
    <ProgressFrame>
      {load.status === 'loading' ? (
        <p role="status" className="m-0 text-fg-soft">
          {M.loading}
        </p>
      ) : null}
      {load.status === 'failed' ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="m-0 text-fg-soft">
            {M.unavailable}
          </p>
          <Button variant="secondary" onClick={reload}>
            {M.retry}
          </Button>
        </div>
      ) : null}
      {load.status === 'ready' ? <ProgressView progress={load.progress} /> : null}
    </ProgressFrame>
  );
}
