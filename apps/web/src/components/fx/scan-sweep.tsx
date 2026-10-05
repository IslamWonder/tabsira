import { cx } from '@/lib/cx';

/**
 * Over a photo being analysed: a soft band of light sweeps down on a loop over a
 * barely tinted edge (the photo stays the subject, not the effect), inside four thin corner brackets. Screen-blended, so it
 * lifts the picture instead of covering it. The parent must be `relative`;
 * under reduced motion the band stays put.
 */
export function ScanSweep({ active, className }: { active: boolean; className?: string }) {
  if (!active) {
    return null;
  }
  return (
    <div
      aria-hidden="true"
      data-scan="active"
      className={cx(
        'pointer-events-none absolute inset-0 overflow-hidden motion-safe:animate-fade-in',
        className
      )}
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(180deg, color-mix(in srgb, var(--glow-emerald) 8%, transparent), transparent 22%, transparent 78%, color-mix(in srgb, var(--glow-emerald) 8%, transparent))',
        }}
      />
      <div className="fx-sweep__band" />
      <span className="fx-bracket fx-bracket--tl" />
      <span className="fx-bracket fx-bracket--tr" />
      <span className="fx-bracket fx-bracket--bl" />
      <span className="fx-bracket fx-bracket--br" />
    </div>
  );
}
