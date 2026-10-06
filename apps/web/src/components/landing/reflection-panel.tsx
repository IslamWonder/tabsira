import type { CSSProperties } from 'react';
import { EmblemTile } from '@/components/ui/emblem';
import { GlassPanel } from '@/components/ui/glass-panel';
import { messages } from '@/messages';
import { KhatamStar } from './hero-atmosphere';

const E = messages.landing.example;

export interface ReflectionPanelProps {
  /** The platform's reflection on the scene: interface copy, never scripture. */
  glimpse: string;
  /** The small step, under the API's own label. */
  smallStep: { label: string; text: string } | null;
}

/**
 * The reflection as a page of a game's journal: an ornate window with its
 * emblem (an eye in focus marks: look closely), a line that invites the reader
 * to slow down, the reflection set large enough to be read, not skimmed, and
 * the small step below it as the quest it is, on its own dashed scroll. It
 * stands apart from the verse and the hadith above it, which never move.
 */
export function ReflectionPanel({ glimpse, smallStep }: Readonly<ReflectionPanelProps>) {
  return (
    <GlassPanel
      as="section"
      ornate
      tone="primary"
      aria-label={E.reflection}
      className="fx-rise relative isolate flex flex-col gap-4 overflow-hidden"
    >
      {/* A khatam turning slowly in the corner, behind everything. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -end-20 -top-20 -z-10 size-60 text-[var(--landing-gold)] opacity-15"
      >
        <KhatamStar className="fx-turn-slow size-full" />
      </span>

      <header className="flex items-center gap-3.5">
        <EmblemTile name="reflect" />
        <div className="flex min-w-0 flex-col">
          <h4 className="m-0 font-bold text-[1.0625rem] text-[var(--landing-gold)]">
            {E.reflection}
          </h4>
          <p className="m-0 text-[0.875rem] text-fg-muted">{E.reflectionHint}</p>
        </div>
      </header>

      <span
        aria-hidden="true"
        className="fx-thread fx-thread--now h-px w-full bg-[linear-gradient(90deg,transparent,var(--landing-gold),transparent)] opacity-60"
        style={{ '--fx-delay': '250ms' } as CSSProperties}
      />

      <p className="m-0 text-[1.1875rem] text-fg leading-[2]">{glimpse}</p>

      {smallStep === null ? null : (
        <div className="flex items-start gap-3.5 rounded-[16px] border border-[color-mix(in_srgb,var(--landing-gold)_45%,transparent)] border-dashed bg-[color-mix(in_srgb,var(--landing-gold)_7%,transparent)] p-4">
          <EmblemTile name="quest" />
          <div className="flex min-w-0 flex-col gap-0.5 pt-0.5">
            <span className="font-semibold text-[0.875rem] text-[var(--landing-gold)]">
              {smallStep.label}
            </span>
            <p className="m-0 text-[0.9875rem] text-fg leading-[1.9]">{smallStep.text}</p>
          </div>
        </div>
      )}
    </GlassPanel>
  );
}
