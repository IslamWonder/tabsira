import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';

const M = messages.practiceView.rank;

/**
 * The practice rank: a name for how
 * many looks were completed, with the way to the next one in view
 * (goal-gradient). The bar fills once on display. Practice, never piety.
 */
export function RankCard({ rank }: { rank: Progress['rank'] }) {
  const next = rank.next === null ? M.top : M.next(rank.next.title, rank.next.minimum);
  return (
    <GlassPanel as="section" ornate aria-labelledby="practice-rank" className="flex flex-col gap-3">
      <p className="m-0 text-[var(--step-title)] text-sm">{M.label}</p>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <h2
          id="practice-rank"
          className="m-0 font-bold font-display text-[2rem] text-gilded leading-[1.3]"
        >
          {rank.title}
        </h2>
        <span className="text-fg-soft text-sm">{M.looks(rank.looks)}</span>
      </div>
      <p className="m-0 text-fg-soft leading-[1.8]">{rank.hint}</p>
      <div
        role="progressbar"
        aria-label={M.progressLabel}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(rank.progress * 100)}
        aria-valuetext={next}
        className="h-2 overflow-hidden rounded-full bg-[var(--border)]"
      >
        <div
          className="h-full origin-left rounded-full bg-[linear-gradient(90deg,var(--glow-gold),var(--glow-emerald))] motion-safe:animate-grow rtl:origin-right"
          style={{ width: `${Math.round(rank.progress * 100)}%` }}
        />
      </div>
      <p className="m-0 text-fg-muted text-sm">{next}</p>
    </GlassPanel>
  );
}
