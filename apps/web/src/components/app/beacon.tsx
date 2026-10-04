import type { ReactNode } from 'react';

/**
 * A still emblem for status screens: the icon inside two thin rings with the
 * glow of an insight point. Decorative; the heading next to it says it all.
 */
export function Beacon({ children }: { children: ReactNode }) {
  return (
    <div aria-hidden="true" className="relative flex size-36 items-center justify-center">
      <span className="absolute inset-0 rounded-full border border-[var(--quran-border)]" />
      <span className="absolute inset-4 rounded-full border border-[var(--sunnah-border)] border-dashed" />
      <span
        className="absolute inset-9 rounded-full"
        style={{
          background:
            'radial-gradient(circle, var(--glow-gold) 0%, transparent 70%), radial-gradient(circle, var(--glow-emerald) 0%, transparent 75%)',
          opacity: 0.35,
        }}
      />
      <span className="glass relative flex size-16 items-center justify-center rounded-full text-primary">
        {children}
      </span>
      <span
        className="absolute top-3 right-6 size-2 rounded-full"
        style={{ background: 'var(--point-gold-core)', boxShadow: '0 0 10px 3px var(--glow-gold)' }}
      />
      <span
        className="absolute bottom-5 left-4 size-1.5 rounded-full"
        style={{
          background: 'var(--point-emerald-core)',
          boxShadow: '0 0 8px 2px var(--glow-emerald)',
        }}
      />
    </div>
  );
}
