import { type ReactNode, useId } from 'react';
import { Logo } from '@/components/brand/logo';
import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';

/**
 * The pointed arch of a gate, drawn behind the panel in the ornament token: a
 * double line, a khatam at the apex and a few still stars. Decorative; the
 * lines draw themselves in once (motion on display only).
 */
function GateArch() {
  // useId's characters are not all valid in a url(#…) reference.
  const fade = `gate-fade-${useId().replace(/[^\w-]/g, '')}`;
  const arch = 'M24 600V250C24 140 110 66 200 18c90 48 176 122 176 232v350';
  const inner = 'M44 600V256C44 156 120 92 200 48c80 44 156 108 156 208v344';
  return (
    <svg
      viewBox="0 0 400 600"
      fill="none"
      aria-hidden="true"
      focusable="false"
      className="block h-auto w-full text-[var(--ornament)]"
    >
      <defs>
        <linearGradient id={fade} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.7" />
          <stop offset="0.75" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        className="fx-draw"
        pathLength={1}
        d={arch}
        stroke={`url(#${fade})`}
        strokeWidth={1.2}
      />
      <path d={inner} stroke={`url(#${fade})`} strokeWidth={0.7} strokeDasharray="2 5" />
      <polygon
        points={starPoints(200, 18, 9, 9 * KHATAM_RATIO)}
        fill="currentColor"
        fillOpacity={0.75}
      />
      {[
        [96, 150, 1.6],
        [318, 120, 1.2],
        [58, 330, 1.1],
        [352, 300, 1.5],
      ].map(([x, y, r]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="currentColor" fillOpacity={0.6} />
      ))}
    </svg>
  );
}

export interface GateProps {
  title: string;
  lead?: ReactNode;
  /** Links under the panel: another way in, the way back. */
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * The account screens as a calm gate over the living background (DESIGN_DECISION.md
 * «Game feel»): the full logo under a faint pointed arch, then one ornate
 * glass window holding one task. No wall of fields: the window holds only
 * what this step needs, and the ways out sit just below it (Occam's razor,
 * Law of Common Region). The panel's title is the page's one heading.
 */
export function Gate({ title, lead, footer, children }: GateProps) {
  const titleId = useId();
  return (
    <div className="relative isolate flex w-full justify-center overflow-hidden px-4 pt-[max(24px,env(safe-area-inset-top))] pb-10 tablet:min-h-[calc(var(--app-height)-var(--topbar-height))] tablet:items-center tablet:py-10">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-24 -z-10 mx-auto h-[28rem] max-w-[36rem] rounded-full opacity-60 blur-3xl"
        style={{
          background:
            'radial-gradient(closest-side, color-mix(in srgb, var(--glow-gold) 30%, transparent), transparent)',
        }}
      />
      <section aria-labelledby={titleId} className="relative w-full max-w-[29rem] pt-16">
        <div className="absolute inset-x-0 top-0 -z-10 flex justify-center">
          <div className="w-[min(44rem,170%)] shrink-0">
            <GateArch />
          </div>
        </div>
        <Logo title={messages.brand.name} className="mx-auto h-28 tablet:h-32" />
        <GlassPanel ornate className="mt-7 flex flex-col gap-5 px-5 pt-7 pb-7 tablet:px-9">
          <header className="flex flex-col items-center gap-2 text-center">
            <h1 id={titleId} className="m-0 font-bold font-display text-title text-gilded">
              {title}
            </h1>
            {lead === undefined ? null : (
              <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.85]">{lead}</p>
            )}
          </header>
          {children}
        </GlassPanel>
        {footer === undefined ? null : (
          <div className="mt-5 flex flex-col items-center gap-1 text-center text-[0.9375rem] text-fg-soft">
            {footer}
          </div>
        )}
      </section>
    </div>
  );
}
