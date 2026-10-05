'use client';

import { type MouseEvent, useEffect, useRef, useState } from 'react';
import { burstFrom } from '@/components/fx/burst';
import { SparkIcon } from '@/components/icons';
import { EvidenceCard } from '@/components/insight/evidence-card';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { revealTreasure, type Treasure } from '@/world/api';

const M = messages.world.treasure;

type State =
  | { status: 'ready' | 'revealing' }
  | { status: 'failed'; message: string }
  | { status: 'revealed'; treasure: Treasure };

function refusal(failure: Failure): string {
  return failure.code === 'TREASURE_NOT_READY' ? M.notReady : failureMessage(failure);
}

/** The verified texts of a treasure, rendered by the same cards as an insight, byte for byte. */
function Evidence({ treasure }: { treasure: Treasure }) {
  const { quran, hadith } = treasure;
  return (
    <div className="flex flex-col gap-3">
      {quran === null ? null : (
        <EvidenceCard
          variant="quran"
          headingLevel={3}
          text={quran.verse.text}
          reference={M.quranReference(quran.verse.surah_name, quran.verse.ayah)}
          verified
        />
      )}
      {hadith === null ? null : (
        <EvidenceCard
          variant="sunnah"
          headingLevel={3}
          text={hadith.hadith.text}
          spans={hadith.hadith.spans}
          reference={M.hadithReference(
            hadith.hadith.collection.name_ar,
            hadith.hadith.arabic_number ?? hadith.hadith.number
          )}
        />
      )}
    </div>
  );
}

function Revealed({ treasure }: { treasure: Treasure }) {
  const heading = useRef<HTMLHeadingElement>(null);
  // The moment is one: focus lands on what was found, so it is read once.
  useEffect(() => (heading.current as HTMLHeadingElement).focus(), []);
  return (
    <GlassPanel
      as="section"
      tone="primary"
      ornate
      aria-labelledby={`treasure-${treasure.id}`}
      className="flex flex-col gap-3 motion-safe:animate-fade-in"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3
          id={`treasure-${treasure.id}`}
          ref={heading}
          tabIndex={-1}
          className="m-0 font-bold font-display text-heading text-gilded outline-none"
        >
          {M.revealedTitle}
        </h3>
        <Chip tone="primary">{treasure.kind_label}</Chip>
      </div>
      <Evidence treasure={treasure} />
      {treasure.learning_unit === null ? null : (
        <p className="m-0 text-fg-soft text-sm leading-[1.8]">
          {M.unit}: {treasure.learning_unit.title}
        </p>
      )}
      <p className="m-0 text-fg-muted text-sm leading-[1.8]">{treasure.disclosure}</p>
    </GlassPanel>
  );
}

/**
 * A hidden treasure waiting in a place: a quiet invitation, then the reveal as
 * a short moment (a burst of light and the panel rising) once the API has
 * returned the verified text. Nothing of the treasure is known before that.
 */
export function TreasureCard({ id }: { id: string }) {
  const [state, setState] = useState<State>({ status: 'ready' });

  async function reveal(event: MouseEvent<HTMLButtonElement>) {
    const button = event.currentTarget;
    setState({ status: 'revealing' });
    const result = await revealTreasure(id);
    if (result.ok) {
      burstFrom(button);
      setState({ status: 'revealed', treasure: result.data });
    } else {
      setState({ status: 'failed', message: refusal(result) });
    }
  }

  if (state.status === 'revealed') {
    return <Revealed treasure={state.treasure} />;
  }
  return (
    <GlassPanel as="section" aria-label={M.title} className="flex flex-col items-start gap-3">
      <h3 className="m-0 flex items-center gap-2 font-bold font-display text-heading text-gilded">
        <SparkIcon width="20" height="20" className="text-[var(--glow-gold)]" />
        {M.title}
      </h3>
      <p className="m-0 text-fg-soft leading-[1.85]">{M.ready}</p>
      {state.status === 'failed' ? (
        <p role="alert" className="m-0 text-danger text-sm">
          {state.message}
        </p>
      ) : null}
      <Button variant="primary" disabled={state.status === 'revealing'} onClick={reveal}>
        {state.status === 'revealing' ? M.revealing : M.reveal}
      </Button>
    </GlassPanel>
  );
}
