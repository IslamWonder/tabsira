'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useId, useState } from 'react';
import { acceptLegal, LEGAL_REFUSAL, type LegalVersions, loadLegal } from '@/account/legal';
import { takeTick, tickMatches } from '@/account/legal-tick';
import { deleteAccount } from '@/account/profile';
import { setGuest, setSignedIn, signOut, type User, useSession } from '@/account/session';
import { useLegal } from '@/account/use-legal';
import { Logo } from '@/components/brand/logo';
import { TrashIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { FullScreenDialog } from '@/components/ui/full-screen-dialog';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { useConsent } from '@/consent/store';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { FullNameConsent } from './full-name-consent';
import { LegalConsent } from './legal-consent';

const L = messages.auth.legal;
/** The texts themselves stay readable while the gate is up: its links open them in place. */
const READABLE = new Set(['/terms', '/privacy']);
const X = messages.pages.me.delete;

/** Deleting the account from the gate: the existing route, confirmed in place, never by a browser dialog. */
function DeleteFromGate({
  busy,
  onFailure,
}: Readonly<{
  busy: boolean;
  onFailure: (message: string) => void;
}>) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const remove = async () => {
    setDeleting(true);
    const result = await deleteAccount();
    setDeleting(false);
    if (result.ok) {
      setGuest();
    } else {
      onFailure(failureMessage(result));
    }
  };
  if (!confirming) {
    return (
      <Button
        variant="ghost"
        disabled={busy}
        onClick={() => setConfirming(true)}
        className="text-danger hover:text-danger"
      >
        <TrashIcon width="18" height="18" />
        {X.title}
      </Button>
    );
  }
  return (
    <section
      aria-label={X.confirmTitle}
      className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-danger bg-surface p-4"
    >
      <p className="m-0 font-semibold text-danger">{X.confirmTitle}</p>
      <p className="m-0 text-fg text-sm leading-[1.85]">{X.confirmBody}</p>
      <div className="flex flex-wrap gap-2.5">
        <Button variant="secondary" disabled={deleting} onClick={() => setConfirming(false)}>
          {X.cancel}
        </Button>
        <Button
          variant="ghost"
          disabled={deleting}
          onClick={remove}
          className="border border-danger text-danger hover:text-danger"
        >
          {deleting ? X.deleting : X.confirm}
        </Button>
      </div>
    </section>
  );
}

function Window({
  user,
  legal,
  onRetry,
}: Readonly<{
  user: User;
  legal: LegalVersions | 'loading' | 'failed';
  onRetry: () => void;
}>) {
  const titleId = useId();
  const bodyId = useId();
  const [accepted, setAccepted] = useState(false);
  const [fullName, setFullName] = useState(user.public_full_name);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const accept = async (versions: LegalVersions) => {
    setBusy(true);
    setFailure(null);
    // Sent only when it changes the answer already given; the box is never ticked for the person.
    const choices = fullName === user.public_full_name ? {} : { public_full_name: fullName };
    const result = await acceptLegal(versions, choices);
    setBusy(false);
    if (result.ok) {
      setSignedIn({ ...user, legal_acceptance_required: false, public_full_name: fullName });
      return;
    }
    if (result.code === LEGAL_REFUSAL) {
      setAccepted(false);
      onRetry();
    }
    setFailure(failureMessage(result));
  };

  const decline = async () => {
    setBusy(true);
    const problem = await signOut();
    setBusy(false);
    if (problem !== null) {
      setFailure(failureMessage(problem));
    }
  };

  return (
    <FullScreenDialog open layer="z-[65]" labelledBy={titleId} describedBy={bodyId}>
      <GlassPanel
        ornate
        className="fx-dialog-surface flex flex-col gap-5 px-5 pt-8 pb-7 tablet:px-10"
      >
        <header className="flex flex-col items-center gap-3 text-center">
          <Logo title={messages.brand.name} className="mb-1 h-24 tablet:h-28" />
          <h2 id={titleId} className="m-0 font-bold font-display text-title text-gilded">
            {L.gate.title}
          </h2>
          <p id={bodyId} className="m-0 text-fg-soft leading-[1.85]">
            {L.gate.body}
          </p>
        </header>
        <LegalConsent
          checked={accepted}
          onChange={setAccepted}
          disabled={typeof legal === 'string'}
          inPlace
        />
        <FullNameConsent checked={fullName} onChange={setFullName} />
        {legal === 'failed' ? (
          <div role="alert" className="flex flex-col items-start gap-1">
            <Notice tone="error">{L.unavailable}</Notice>
            <Button variant="ghost" onClick={onRetry}>
              {L.retry}
            </Button>
          </div>
        ) : null}
        {failure === null ? null : (
          <div role="alert">
            <Notice tone="error">{failure}</Notice>
          </div>
        )}
        <div className="grid gap-3 tablet:grid-cols-2">
          <Button
            size="lg"
            disabled={busy || !accepted || typeof legal === 'string'}
            onClick={() => accept(legal as LegalVersions)}
          >
            {busy ? L.gate.accepting : L.gate.accept}
          </Button>
          <Button variant="ghost" size="lg" disabled={busy} onClick={decline}>
            {L.gate.decline}
          </Button>
        </div>
        <div className="flex justify-center border-line border-t pt-3">
          <DeleteFromGate busy={busy} onFailure={setFailure} />
        </div>
      </GlassPanel>
    </FullScreenDialog>
  );
}

/**
 * The acceptance asked again (owner decision 35): when the API says the
 * signed-in account has not accepted the current terms and privacy policy
 * (a new version, or an account just created with Google from the sign-in
 * page), a full-screen window asks for the same box before anything else.
 * Declining signs out, and the account can be deleted from here too; nothing
 * else is held back from a guest. It waits for
 * the cookie choice, and never covers the texts it links to.
 */
export function LegalGate() {
  const session = useSession();
  const pathname = usePathname();
  const { consent, settingsOpen } = useConsent();
  if (
    session.status !== 'signed-in' ||
    session.user.legal_acceptance_required !== true ||
    READABLE.has(pathname) ||
    consent.status === 'asking' ||
    settingsOpen
  ) {
    return null;
  }
  return <LegalGateWindow user={session.user} />;
}

/**
 * Back from Google after ticking the box on the sign-up view: a fresh tick
 * for exactly the texts in force is recorded at once, and the gate never
 * shows. Anything else (no tick, a stale or used one, other versions) asks.
 */
function useTickAccepted(user: User): 'checking' | 'ask' {
  const [state, setState] = useState<'checking' | 'ask'>('checking');
  useEffect(() => {
    const tick = takeTick();
    if (tick === null) {
      setState('ask');
      return;
    }
    void (async () => {
      const legal = await loadLegal();
      const accepted =
        legal.ok &&
        tickMatches(tick, legal.data) &&
        (await acceptLegal(legal.data, { public_full_name: tick.public_full_name })).ok;
      if (accepted) {
        setSignedIn({ ...user, legal_acceptance_required: false });
      } else {
        setState('ask');
      }
    })();
  }, [user]);
  return state;
}

function LegalGateWindow({ user }: { user: User }) {
  const tick = useTickAccepted(user);
  return tick === 'checking' ? null : <AskingWindow user={user} />;
}

function AskingWindow({ user }: Readonly<{ user: User }>) {
  const legal = useLegal();
  const state = legal.state;
  return (
    <Window
      user={user}
      legal={state.status === 'ready' ? state.legal : state.status}
      onRetry={legal.reload}
    />
  );
}
