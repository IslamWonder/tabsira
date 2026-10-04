'use client';

import type { Route } from 'next';
import { useEffect, useId, useRef } from 'react';
import { SaveInvitation } from '@/components/account/save-invitation';
import { CheckIcon } from '@/components/icons';
import { Button, LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import type { Completion, Progress } from '@/lib/scan/api';
import { messages } from '@/messages';
import { PlaceReveal } from './place-reveal';

const T = messages.completion;

export interface CompletionPanelProps {
  completion: Completion;
  /** The learner's practice after this completion; null while it loads or when it could not be read. */
  progress: Progress | null;
  /** The practice could not be read: say so, and keep what the done action itself returned. */
  progressFailed: boolean;
  /** Where the reader comes back to after creating an account: this insight. */
  returnTo: Route;
  onContinueAsGuest: () => void;
  /** The guest chose to continue as one: the invitation is not asked again in this visit. */
  invitationClosed: boolean;
  /** The third option: open the share sheet, or the one-line reason it cannot be opened. */
  share: ShareOption;
}

export type ShareOption =
  | { kind: 'open'; onOpen: () => void }
  | { kind: 'blocked'; reason: string };

/**
 * What the done action earned, each thing only once the save has succeeded (tajriba §7,
 * A04): the place the fog lifted from, the day's quest, a practice badge,
 * then the way on: the world first, another scene next, sharing third (v2 §4.8).
 * The API's share option is a button when the API lists it and the owner may
 * publish; otherwise the reason stands in its place, in one line, so nothing is
 * silently missing. Practice, never
 * piety: the disclaimer stands wherever a badge does (decision 27). Focus
 * moves here when it appears, so a screen reader hears it and a phone shows it.
 */
export function CompletionPanel({
  completion,
  progress,
  progressFailed,
  returnTo,
  onContinueAsGuest,
  invitationClosed,
  share,
}: CompletionPanelProps) {
  const titleId = useId();
  const region = useRef<HTMLElement>(null);
  const { place } = completion;
  const badges = (progress?.badges ?? []).filter((badge) =>
    completion.badges_earned.includes(badge.id)
  );
  const label = (id: 'open_world' | 'new_scan', fallback: string) =>
    completion.options.find((option) => option.id === id)?.label ?? fallback;
  const shareOption = completion.options.find((option) => option.id === 'share');
  const shareReason =
    share.kind === 'blocked' ? share.reason : shareOption === undefined ? T.shareUnavailable : null;

  useEffect(() => {
    const element = region.current as HTMLElement;
    element.focus({ preventScroll: true });
    element.scrollIntoView({ block: 'center' });
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <section ref={region} aria-labelledby={titleId} tabIndex={-1} className="outline-none">
        <GlassPanel ornate tone="primary" className="flex flex-col gap-4">
          <h2 id={titleId} className="m-0 font-bold font-display text-[1.5rem] text-gilded">
            {T.title}
          </h2>

          {place === null ? null : (
            <p className="m-0 flex items-center gap-3 text-[1.0625rem] text-fg leading-[1.8]">
              <PlaceReveal created={place.created} />
              {place.created ? T.placeNew(place.name) : T.placeSeen(place.name)}
            </p>
          )}
          {completion.treasure_prepared ? (
            <p className="m-0 text-fg-soft leading-[1.8]">{T.treasure}</p>
          ) : null}

          {progress === null ? null : (
            <section aria-label={T.quest} className="flex flex-col gap-2">
              <h3 className="m-0 font-semibold text-[0.9375rem] text-fg-soft">
                {T.quest}: {progress.daily_quest.title}
              </h3>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {progress.daily_quest.steps.map((step) => (
                  <li key={step.id} className="flex items-center gap-2 text-[0.9375rem] text-fg">
                    {step.done ? (
                      <CheckIcon width="18" height="18" className="shrink-0 text-primary" />
                    ) : (
                      <span
                        aria-hidden="true"
                        className="size-2.5 shrink-0 rotate-45 border border-line"
                      />
                    )}
                    <span>{step.label}</span>
                    {step.done ? <span className="sr-only">{T.questStepDone}</span> : null}
                  </li>
                ))}
              </ul>
              {progress.daily_quest.done ? (
                <p className="m-0 font-medium text-[0.9375rem] text-primary">{T.questDone}</p>
              ) : null}
            </section>
          )}

          {badges.length === 0 ? null : (
            <section aria-label={T.badges} className="flex flex-col gap-2">
              <h3 className="m-0 font-semibold text-[0.9375rem] text-fg-soft">{T.badges}</h3>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {badges.map((badge) => (
                  <li key={badge.id} className="flex flex-col">
                    <span className="font-semibold text-fg">{badge.title}</span>
                    <span className="text-[0.9375rem] text-fg-soft">{badge.description}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {progress === null || (badges.length === 0 && !progress.daily_quest.done) ? null : (
            <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.7]">
              {progress.disclaimer}
            </p>
          )}
          {progressFailed ? <Notice tone="info">{T.progressFailed}</Notice> : null}

          <div className="flex flex-col gap-2.5 tablet:flex-row">
            <LinkButton href="/world" size="lg" className="flex-1">
              {label('open_world', T.openWorld)}
            </LinkButton>
            <LinkButton href="/" variant="secondary" size="lg" className="flex-1">
              {label('new_scan', T.newScan)}
            </LinkButton>
            {shareOption !== undefined && share.kind === 'open' ? (
              <Button variant="secondary" size="lg" className="flex-1" onClick={share.onOpen}>
                {shareOption.label}
              </Button>
            ) : null}
          </div>
          {shareReason === null ? null : (
            <p className="m-0 text-[0.9375rem] text-fg-muted leading-[1.7]">{shareReason}</p>
          )}
        </GlassPanel>
      </section>

      {completion.suggest_account === null || invitationClosed ? null : (
        <SaveInvitation returnTo={returnTo} onContinueAsGuest={onContinueAsGuest} />
      )}
    </div>
  );
}
