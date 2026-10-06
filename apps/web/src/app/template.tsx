import { type ReactNode, ViewTransition } from 'react';

/**
 * Every navigation: the page fades in while a thin band of gold light sweeps
 * along the top edge, a scene change. Opacity only on the page wrapper, so
 * fixed layers (the bars, sheets) keep their place (AGENTS.md lessons). Where
 * the browser has view transitions the page left behind also fades out
 * (`page-leave` in fx.css), so the two cross instead of the new one popping
 * over the old; elsewhere the fade-in alone plays.
 */
export default function Template({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <span
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-0 top-0 z-[80] h-0.5 origin-right opacity-0 animate-[fx-route_0.9s_cubic-bezier(0.22,1,0.36,1)]"
        style={{ background: 'linear-gradient(90deg, transparent, var(--glow-gold), transparent)' }}
      />
      <ViewTransition exit="page-leave" enter="none" default="none">
        <div className="motion-safe:animate-fade-in">{children}</div>
      </ViewTransition>
    </>
  );
}
