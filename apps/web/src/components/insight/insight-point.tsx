import { type CSSProperties, useId } from 'react';
import { SparkIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import type { HorizontalSide, VerticalSide } from './scene-geometry';

export type PointTone = 'gold' | 'emerald';

export interface InsightPointProps {
  id: string;
  title: string;
  glimpse?: string;
  tone?: PointTone;
  /** Position of the orb's centre, in percent of the photo box. */
  left: number;
  top: number;
  /** The label hangs below the orb, or above it in the lower half of the photo. */
  vertical: VerticalSide;
  /** Near a side the label grows toward the middle instead of centring on the orb. */
  horizontal?: HorizontalSide;
  /** Where the point is, in words, for screen readers. */
  positionLabel: string;
  selected?: boolean;
  /** Seconds before the glow starts breathing, so two points do not pulse in step. */
  delay?: number;
  /**
   * The scan asks the reader to choose (fx.css «sheen»): a gold light runs over the label
   * with the rings, and both play again each time `calls` grows (an idle reader).
   */
  invite?: boolean;
  calls?: number;
  onSelect: (id: string) => void;
}

// The orb (56 px) keeps its centre on the point: centred, or 28 px in from the
// side the label grows away from. The page is right-to-left, so a column's
// cross-axis "end" is its physical left.
const SHIFT: Record<HorizontalSide, { translate: string; align: string }> = {
  center: { translate: '-50%', align: 'items-center' },
  toRight: { translate: '-28px', align: 'items-end' },
  toLeft: { translate: 'calc(-100% + 28px)', align: 'items-start' },
};

const TONES: Record<PointTone, { core: string; halo: string }> = {
  gold: { core: 'var(--point-gold-core)', halo: 'var(--point-gold-halo)' },
  emerald: { core: 'var(--point-emerald-core)', halo: 'var(--point-emerald-halo)' },
};

/**
 * An insight on the photo: a glowing orb inside a thin gold ring, with a
 * two-line glass label, as one real button (the earlier prototype's hotspot,
 * the owners' choice). Two rings call once from the orb and its halo breathes
 * twice when the scene appears, then everything rests: under five seconds, so
 * no pause control is needed (WCAG 2.2.2), and nothing moves under reduced
 * motion. Selective attention: two calm lights, nothing else on the photo moves.
 * When the scan asks the reader to choose, a gold light also runs over the label,
 * and the call comes back after a long stillness (see `invite`). The title turns
 * gold under the pointer, which shows the hand: colour only, nothing moves.
 */
export function InsightPoint({
  id,
  title,
  glimpse,
  tone = 'gold',
  left,
  top,
  vertical,
  horizontal = 'center',
  positionLabel,
  selected = false,
  delay = 0,
  invite = false,
  calls = 0,
  onSelect,
}: Readonly<InsightPointProps>) {
  const colours = TONES[tone];
  const titleId = useId();
  const glimpseId = useId();
  const positionId = useId();
  const above = vertical === 'above';
  const x = SHIFT[horizontal];

  const ring: CSSProperties = { borderColor: colours.halo, animationDelay: `${delay}s` };

  return (
    <button
      type="button"
      data-point-id={id}
      // Named by its title alone; the glimpse and the place in the photo follow as its description.
      aria-labelledby={titleId}
      aria-describedby={glimpse === undefined ? positionId : `${glimpseId} ${positionId}`}
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelect(id)}
      className={cx(
        'group absolute z-10 flex w-max max-w-[min(14rem,64vw)] gap-2',
        x.align,
        above ? 'flex-col-reverse' : 'flex-col'
      )}
      style={{
        left: `${left}%`,
        top: `${top}%`,
        // The orb's centre sits on the point, whichever side the label takes.
        transform: `translate(${x.translate}, ${above ? 'calc(-100% + 28px)' : '-28px'})`,
      }}
    >
      <span
        aria-hidden="true"
        className="relative flex size-14 shrink-0 items-center justify-center"
      >
        <span
          className="absolute -inset-5 rounded-full opacity-60 blur-md motion-safe:animate-breathe"
          style={{
            background: `radial-gradient(circle, ${colours.halo} 0%, transparent 70%)`,
            animationDelay: `${delay}s`,
          }}
        />
        {selected ? null : (
          <>
            {/* Keyed by the calls, so an idle reader sees them leave the orb again. */}
            <span
              key={`first-${calls}`}
              className="absolute inset-0 rounded-full border-2 opacity-0 motion-safe:animate-[fx-ring_2.4s_cubic-bezier(0.22,1,0.36,1)_2]"
              style={{ ...ring, animationDelay: `${calls > 0 ? 0 : delay}s` }}
            />
            <span
              key={`second-${calls}`}
              className="absolute inset-0 rounded-full border-2 opacity-0 motion-safe:animate-[fx-ring_2.4s_cubic-bezier(0.22,1,0.36,1)_2]"
              style={{ ...ring, animationDelay: `${(calls > 0 ? 0 : delay) + 0.8}s` }}
            />
          </>
        )}
        <span
          className={cx(
            'glass relative flex size-14 items-center justify-center rounded-full border-[1.5px] transition-[background-color,box-shadow] duration-300',
            selected && 'shadow-[0_0_0_3px_var(--focus)]'
          )}
          style={{
            borderColor: colours.halo,
            boxShadow: `0 0 30px color-mix(in srgb, ${colours.halo} 55%, transparent), inset 0 0 14px color-mix(in srgb, ${colours.halo} 35%, transparent)`,
          }}
        >
          <span
            className="absolute inset-[30%] rounded-full"
            style={{ background: colours.core, boxShadow: `0 0 14px 5px ${colours.halo}` }}
          />
          <SparkIcon
            width="22"
            height="22"
            className="relative text-[var(--on-primary)] opacity-80"
          />
        </span>
      </span>
      <span className="glass relative flex flex-col items-center rounded-[14px] px-3.5 py-1.5 text-center">
        {invite && !selected ? (
          <span
            key={calls}
            aria-hidden="true"
            className="fx-sheen"
            style={{ '--fx-delay': `${(calls > 0 ? 0 : delay) * 1000 + 300}ms` } as CSSProperties}
          />
        ) : null}
        <span
          id={titleId}
          className="font-semibold text-[1.0625rem] text-glass-fg leading-snug transition-colors duration-200 group-hover:text-[var(--glow-gold)]"
        >
          {title}
        </span>
        {/* Real spaces between the lines: a text extractor ignores the block layout and would weld the words. */}
        {glimpse === undefined ? null : (
          <>
            {' '}
            <span id={glimpseId} className="text-[0.8125rem] text-glass-fg-soft leading-snug">
              {glimpse}
            </span>
          </>
        )}{' '}
        <span id={positionId} className="sr-only">
          {positionLabel}
        </span>
      </span>
    </button>
  );
}
