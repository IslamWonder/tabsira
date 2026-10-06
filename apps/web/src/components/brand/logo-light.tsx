/** Where the sparks rise from around the mark, and when (fx.css «logo entrance»). */
const SPARKS = [
  { left: '18%', top: '30%', delay: '1150ms' },
  { left: '78%', top: '22%', delay: '1250ms' },
  { left: '64%', top: '82%', delay: '1350ms' },
  { left: '30%', top: '76%', delay: '1450ms' },
] as const;

/**
 * The light of the logo's entrance, laid behind the mark it frames: a flare, a
 * ring that opens as the last stroke lands, and four sparks. Decorative; it
 * plays once when it first paints (fx.css «logo entrance»).
 */
export function LogoLight({ spark = 'size-1' }: Readonly<{ spark?: string }>) {
  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0">
      <span className="fx-logo-flare absolute inset-[-30%] rounded-full" />
      <span className="fx-logo-ring absolute inset-[-6%] rounded-full border border-[var(--glow-gold)]" />
      {SPARKS.map((item) => (
        <span
          key={item.delay}
          className={`fx-logo-spark absolute rounded-full bg-[var(--glow-gold)] ${spark}`}
          style={{ left: item.left, top: item.top, animationDelay: item.delay }}
        />
      ))}
    </span>
  );
}
