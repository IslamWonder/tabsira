import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { LockIcon } from '@/components/icons';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { formatDay } from '@/lib/dates';
import { messages } from '@/messages';
import type { Badge } from '@/progress/api';

const M = messages.practiceView.badges;

function Medal({ earned }: Readonly<{ earned: boolean }>) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        'flex size-12 shrink-0 items-center justify-center rounded-full border',
        earned
          ? 'border-[var(--quran-border)] bg-[var(--chip-primary-bg)] shadow-[0_0_18px_var(--mark-glow)]'
          : 'border-line bg-surface text-fg-muted'
      )}
    >
      {earned ? (
        <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <polygon
            points={starPoints(12, 12, 11, 11 * KHATAM_RATIO)}
            style={{ fill: 'var(--mark)' }}
          />
        </svg>
      ) : (
        <LockIcon width="20" height="20" />
      )}
    </span>
  );
}

/**
 * The practice badges: each with the API's title and the way it is earned, a
 * lock until then. A locked badge states its rule, which is guidance and not
 * a spoiler. Badges mark practice and steadiness, never faith or acceptance,
 * so the practice disclaimer stays beside them.
 */
export function BadgeGrid({ badges }: Readonly<{ badges: readonly Badge[] }>) {
  const earned = badges.filter((badge) => badge.earned).length;
  return (
    <GlassPanel as="section" aria-labelledby="practice-badges" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="practice-badges" className="m-0 font-bold font-display text-heading text-fg">
          {M.title}
        </h2>
        <span className="text-fg-soft text-sm">{M.count(earned, badges.length)}</span>
      </div>
      <ul className="m-0 grid list-none grid-cols-1 gap-2 p-0 tablet:grid-cols-2 desktop:grid-cols-3">
        {badges.map((badge) => (
          <li
            key={badge.id}
            data-earned={badge.earned}
            className={cx(
              'flex items-center gap-3 rounded-[var(--radius-card)] border border-line p-3',
              badge.earned ? 'bg-surface' : 'bg-transparent'
            )}
          >
            <Medal earned={badge.earned} />
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className={cx('font-semibold', badge.earned ? 'text-fg' : 'text-fg-soft')}>
                {badge.title}
                <span className="sr-only"> {badge.earned ? M.earned : M.locked}</span>
              </span>
              <span className="text-fg-muted text-sm leading-snug">{badge.description}</span>
              {badge.earned_at === null ? null : (
                <span className="text-fg-muted text-xs">{formatDay(badge.earned_at)}</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </GlassPanel>
  );
}
