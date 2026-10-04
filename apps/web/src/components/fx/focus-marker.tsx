import { cx } from '@/lib/cx';

/** A box as 0–1 ratios of the photo, as the server sends detections. */
export interface MarkerBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FocusMarkerProps {
  box: MarkerBox;
  /** Names the object; the accessible name of the button. */
  label: string;
  selected?: boolean;
  /** Recedes when another marker is chosen. */
  dim?: boolean;
  /** Seconds before the lock-on, to stagger several markers. */
  delay?: number;
  onSelect: () => void;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value)) * 100;

/**
 * A detected object on the photo, for choosing the focus (tajriba S08): four
 * gold brackets lock on over a faint fill, with the object's name in a small
 * glass chip. A real button (Enter and Space choose it), pressed when chosen.
 * Positions are ratios of an uncropped photo box.
 */
export function FocusMarker({
  box,
  label,
  selected = false,
  dim = false,
  delay = 0,
  onSelect,
}: FocusMarkerProps) {
  const chipInside = box.y < 0.08;
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cx(
        'absolute rounded-[4px] transition-opacity duration-300',
        'motion-safe:animate-[fx-lock_0.6s_cubic-bezier(0.22,1,0.36,1)_both]',
        dim && !selected && 'opacity-40'
      )}
      style={{
        left: `${clamp(box.x)}%`,
        top: `${clamp(box.y)}%`,
        width: `${clamp(box.width)}%`,
        height: `${clamp(box.height)}%`,
        animationDelay: `${delay}s`,
      }}
    >
      <span
        aria-hidden="true"
        className={cx(
          'absolute inset-0 rounded-[inherit] border',
          selected
            ? 'border-[color-mix(in_srgb,var(--glow-gold)_55%,transparent)] bg-[color-mix(in_srgb,var(--glow-gold)_14%,transparent)] shadow-[0_0_18px_color-mix(in_srgb,var(--glow-gold)_40%,transparent)]'
            : 'border-[color-mix(in_srgb,var(--glow-gold)_25%,transparent)] bg-[color-mix(in_srgb,var(--glow-gold)_6%,transparent)]'
        )}
      />
      <span aria-hidden="true" className="fx-bracket fx-bracket--tl !top-0 !left-0" />
      <span aria-hidden="true" className="fx-bracket fx-bracket--tr !top-0 !right-0" />
      <span aria-hidden="true" className="fx-bracket fx-bracket--bl !bottom-0 !left-0" />
      <span aria-hidden="true" className="fx-bracket fx-bracket--br !bottom-0 !right-0" />
      <span
        className={cx(
          'absolute right-0 max-w-[max(100%,11rem)] truncate rounded-md border px-2 text-[0.8125rem] leading-6',
          chipInside ? 'top-1.5 right-1.5' : 'bottom-full mb-1.5',
          selected
            ? 'border-transparent bg-[var(--glow-gold)] text-[var(--on-primary)]'
            : 'glass text-glass-fg'
        )}
      >
        {label}
      </span>
    </button>
  );
}
