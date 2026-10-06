'use client';

import { usePathname } from 'next/navigation';
import { type FormEvent, useEffect, useId, useRef, useState } from 'react';
import { Logo } from '@/components/brand/logo';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { FullScreenDialog } from '@/components/ui/full-screen-dialog';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { SwitchField } from '@/components/ui/switch-field';
import {
  ACCEPT_ALL,
  type ConsentChoices,
  type ConsentPolicy,
  REJECT_ALL,
} from '@/consent/contract';
import {
  type AskReason,
  type ConsentStatus,
  closeConsentSettings,
  decide,
  loadPolicy,
  type ServerConsent,
  useSeededConsent,
} from '@/consent/store';
import { messages } from '@/messages';

const T = messages.consent;

const REASK: Partial<Record<AskReason, string>> = {
  version: T.reaskVersion,
  time: T.reaskTime,
};

/** The choices the customise view starts from: the recorded ones, else nothing ticked. */
function startingChoices(consent: ConsentStatus): ConsentChoices {
  return consent.status === 'decided' ? consent.record.categories : REJECT_ALL;
}

function Categories({
  policy,
  choices,
  onToggle,
}: Readonly<{
  policy: ConsentPolicy;
  choices: ConsentChoices;
  onToggle: (choices: ConsentChoices) => void;
}>) {
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {policy.categories.map((category) => {
        const fixed = category.key === 'necessary' || category.required;
        return (
          <li
            key={category.key}
            className="rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3"
          >
            <SwitchField
              name={category.key}
              label={category.title}
              hint={
                fixed ? (
                  <>
                    {category.description}{' '}
                    <Chip tone="primary" className="ms-1 align-middle">
                      {T.always}
                    </Chip>
                  </>
                ) : (
                  category.description
                )
              }
              checked={fixed || choices[category.key]}
              disabled={fixed}
              onChange={(on) => onToggle({ ...choices, [category.key]: on })}
            />
          </li>
        );
      })}
    </ul>
  );
}

type Choice = 'accept' | 'reject' | 'customise' | 'save' | 'back';

/**
 * The cookie choice, over the whole screen, in the product's own design
 * (owner decision 32): accept all, reject all and customise side by side
 * with the same weight, nothing ticked in advance, and no wall: rejecting
 * closes it and every part of TABSIRA works. The web server renders it open
 * from the first byte when a choice is needed (src/consent/server.ts), with
 * the page visible but inert under it.
 *
 * It is a real form: without JavaScript its buttons post to /consent, which
 * records the choice and comes back; with JavaScript the same buttons do it
 * in place. Shown on a first visit, when the policy version changed, after
 * its re-ask delay, and whenever the visitor reopens it.
 */
export function ConsentScreen({ initial }: Readonly<{ initial: ServerConsent }>) {
  const { consent, policy, settingsOpen } = useSeededConsent(initial);
  const pathname = usePathname();
  const visible = consent.status === 'asking' || settingsOpen;
  const titleId = useId();
  const leadId = useId();
  const customiseTitleRef = useRef<HTMLHeadingElement>(null);
  const customiseButtonRef = useRef<HTMLButtonElement>(null);
  const [view, setView] = useState<'summary' | 'customise'>(initial.view);
  const [choices, setChoices] = useState<ConsentChoices>(() => startingChoices(consent));
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(initial.failed);
  // Reopened over a recorded choice: it can be left unchanged.
  const canClose = settingsOpen && consent.status !== 'asking';
  const opened = useRef(visible);

  // A reopening starts on the summary, from the recorded choice.
  useEffect(() => {
    if (visible && !opened.current) {
      setView('summary');
      setFailed(false);
    }
    opened.current = visible;
  }, [visible]);

  if (!visible) {
    return null;
  }

  const choose = async (picked: ConsentChoices) => {
    setSaving(true);
    setFailed(false);
    const recorded = await decide(picked);
    setSaving(false);
    setFailed(!recorded && picked !== REJECT_ALL);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter;
    const choice = submitter?.getAttribute('value') as Choice;
    if (choice === 'customise') {
      setChoices(startingChoices(consent));
      setView('customise');
      void loadPolicy();
      // After React shows the list: the heading of the new view takes focus.
      requestAnimationFrame(() => customiseTitleRef.current?.focus());
    } else if (choice === 'back') {
      setView('summary');
      requestAnimationFrame(() => customiseButtonRef.current?.focus());
    } else {
      void choose(choice === 'accept' ? ACCEPT_ALL : choice === 'reject' ? REJECT_ALL : choices);
    }
  };

  const reask = consent.status === 'asking' ? REASK[consent.reason] : undefined;
  const choice = (value: Choice) => ({ type: 'submit' as const, name: 'choice', value });

  return (
    <FullScreenDialog
      open
      labelledBy={titleId}
      describedBy={leadId}
      onEscape={canClose ? closeConsentSettings : undefined}
    >
      <form method="post" action="/consent" onSubmit={submit} aria-busy={saving}>
        <input type="hidden" name="return" value={pathname} />
        {policy.status === 'ready' ? (
          <input type="hidden" name="policy_version" value={policy.policy.policy_version} />
        ) : null}
        <GlassPanel
          ornate
          className="fx-dialog-surface flex flex-col gap-5 px-5 pt-8 pb-6 tablet:px-10"
        >
          <header className="flex flex-col items-center gap-3 text-center">
            <Logo title={messages.brand.name} className="fx-enter mb-1 h-24 tablet:h-28" />
            <h2
              id={titleId}
              className="fx-enter fx-enter--2 m-0 font-bold font-display text-title text-gilded"
            >
              {T.title}
            </h2>
            {reask === undefined ? null : <Chip tone="primary">{reask}</Chip>}
            <div
              id={leadId}
              className="fx-enter fx-enter--2 flex flex-col gap-2 text-fg-soft leading-[1.85]"
            >
              <p className="m-0">{T.lead}</p>
              <p className="m-0">{T.never}</p>
            </div>
          </header>

          {view === 'summary' ? (
            <div className="fx-enter fx-enter--3 flex flex-col gap-3">
              <div className="grid gap-3 tablet:grid-cols-3">
                <Button {...choice('accept')} variant="secondary" size="lg" disabled={saving}>
                  {T.acceptAll}
                </Button>
                <Button {...choice('reject')} variant="secondary" size="lg" disabled={saving}>
                  {T.rejectAll}
                </Button>
                <Button
                  {...choice('customise')}
                  ref={customiseButtonRef}
                  variant="secondary"
                  size="lg"
                  disabled={saving}
                >
                  {T.customise}
                </Button>
              </div>
              <p className="m-0 text-center text-fg-muted text-sm leading-[1.8]">{T.free}</p>
            </div>
          ) : (
            <section aria-labelledby={`${titleId}-customise`} className="flex flex-col gap-4">
              <h3
                ref={customiseTitleRef}
                id={`${titleId}-customise`}
                tabIndex={-1}
                className="m-0 text-fg text-lg outline-none"
              >
                {T.customiseTitle}
              </h3>
              {policy.status === 'ready' ? (
                <Categories policy={policy.policy} choices={choices} onToggle={setChoices} />
              ) : policy.status === 'failed' ? (
                <div className="flex flex-col items-start gap-2">
                  <Notice tone="error">{T.policyFailed}</Notice>
                  <Button variant="ghost" onClick={() => void loadPolicy()}>
                    {T.retry}
                  </Button>
                </div>
              ) : (
                <p role="status" className="m-0 text-fg-muted">
                  {T.policyLoading}
                </p>
              )}
              <div className="grid gap-3 tablet:grid-cols-2">
                <Button
                  {...choice('save')}
                  variant="secondary"
                  size="lg"
                  disabled={saving || policy.status !== 'ready'}
                >
                  {T.save}
                </Button>
                <Button {...choice('back')} variant="ghost" size="lg" disabled={saving}>
                  {T.back}
                </Button>
              </div>
            </section>
          )}

          <div role="status" className="empty:-mb-5">
            {saving ? <p className="m-0 text-center text-fg-soft">{T.saving}</p> : null}
          </div>
          {failed ? (
            <div role="alert">
              <Notice tone="error">{T.saveFailed}</Notice>
            </div>
          ) : null}

          <footer className="flex flex-wrap items-center justify-between gap-2 border-line border-t pt-4">
            <p className="m-0 text-fg-muted text-sm">
              {policy.status === 'ready' ? (
                <>
                  {T.version('')}
                  <bdi dir="ltr">{policy.policy.policy_version}</bdi>
                </>
              ) : null}
            </p>
            {canClose ? (
              <Button variant="ghost" onClick={closeConsentSettings}>
                {T.close}
              </Button>
            ) : null}
          </footer>
        </GlassPanel>
      </form>
    </FullScreenDialog>
  );
}
