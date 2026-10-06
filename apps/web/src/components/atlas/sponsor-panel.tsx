'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { type FormEvent, useEffect, useState } from 'react';
import { signInHref } from '@/account/links';
import { useSession } from '@/account/session';
import { endSponsorship, mySponsorships, sponsorEntry, writeReflection } from '@/atlas/api';
import type { AtlasEntry, Sponsorship } from '@/atlas/types';
import { IdentityForm } from '@/components/community/identity-section';
import { AccessNote, ReportSheet } from '@/components/community/sheets';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { TextArea } from '@/components/ui/text-area';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { profilePath } from '@/social/identity';
import { useIdentity } from '@/social/identity-store';

const S = messages.atlas.sponsor;
const REFLECTION_MAX = 500;

/** Why a 409 CONFLICT was answered: the entry as it is now tells which of the three it was. */
function conflictMessage(entry: AtlasEntry | null): string {
  if (entry === null) {
    return S.refusal.unavailable;
  }
  if (entry.sponsor != null) {
    return S.refusal.already;
  }
  return entry.orphaned ? S.refusal.own : S.refusal.notOrphaned;
}

/** The sentence for a refused sponsoring, one for every refusal the API gives. */
function refusalMessage(failure: Failure, fresh: AtlasEntry | null): string {
  switch (failure.code) {
    case 'CONFLICT':
      return conflictMessage(fresh);
    case 'UNDER_13_CANNOT_PUBLISH':
      return S.refusal.under13;
    case 'PUBLIC_IDENTITY_REQUIRED':
      return S.refusal.identity;
    case 'FORBIDDEN':
    case 'EMAIL_NOT_VERIFIED':
      return S.refusal.verify;
    case 'NOT_FOUND':
      return S.refusal.unavailable;
    default:
      return failureMessage(failure);
  }
}

function SponsorLine({
  sponsor,
  social,
}: Readonly<{
  sponsor: NonNullable<AtlasEntry['sponsor']>;
  social: boolean;
}>) {
  const name = (
    <>
      {sponsor.public_name === null ? null : <>{sponsor.public_name} </>}
      <bdi dir="ltr">@{sponsor.handle}</bdi>
    </>
  );
  return (
    <p className="m-0 text-fg">
      <strong className="font-semibold">{S.entry.by}</strong>{' '}
      {social ? (
        <Link
          href={profilePath(sponsor.handle)}
          className="text-link underline-offset-4 hover:underline"
        >
          {name}
        </Link>
      ) : (
        name
      )}
    </p>
  );
}

function ReflectionForm({
  entry,
  refresh,
}: Readonly<{
  entry: AtlasEntry;
  refresh: () => Promise<unknown>;
}>) {
  const [current, setCurrent] = useState<Sponsorship | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // The sponsor's own reflection in any state, which the public entry shows only once published.
  useEffect(() => {
    let live = true;
    void mySponsorships().then((result) => {
      if (!live || !result.ok) {
        return;
      }
      const mine = result.data.find((item) => item.entry_id === entry.id) ?? null;
      setCurrent(mine);
      setText(mine?.reflection ?? '');
    });
    return () => {
      live = false;
    };
  }, [entry.id]);

  const length = Array.from(text).length;
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    const result = await writeReflection(entry.id, text.trim());
    setBusy(false);
    if (result.ok) {
      setCurrent(result.data);
      setText(result.data.reflection ?? text.trim());
      void refresh();
    } else {
      setProblem(
        result.code === 'VALIDATION_ERROR' ? S.reflection.scripture : failureMessage(result)
      );
    }
  };

  return (
    <form onSubmit={save} aria-label={S.reflection.label} className="flex flex-col gap-3">
      <TextArea
        label={S.reflection.label}
        hint={S.reflection.hint}
        value={text}
        maxChars={REFLECTION_MAX}
        onChange={(event) => setText(event.target.value)}
      />
      {problem === null ? null : (
        <div role="alert">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
      {current?.reflection_status == null ? null : (
        <div role="status" className="flex flex-col items-start gap-2">
          <Chip tone={current.reflection_status === 'published' ? 'primary' : 'neutral'}>
            {S.reflection.status}: {S.reflection.statuses[current.reflection_status]}
          </Chip>
          {current.reflection_message === null ? null : (
            <p className="m-0 text-fg-soft text-sm leading-[1.8]">{current.reflection_message}</p>
          )}
        </div>
      )}
      <Button
        type="submit"
        variant="secondary"
        disabled={busy || text.trim() === '' || length > REFLECTION_MAX}
        className="self-start"
      >
        {busy ? S.reflection.saving : S.reflection.save}
      </Button>
    </form>
  );
}

/**
 * Sponsoring on the entry's page (decision 60). An orphaned entry offers
 * the sponsor action to a verified member with a public identity, and to others the
 * missing step; a sponsored one names its sponsor and shows the published reflection;
 * the sponsor alone gets the end action (after a confirmation) and the reflection form.
 * Nothing here counts or rewards. The server judges every action; this only says why not.
 */
export function SponsorPanel({
  entry,
  social,
  refresh,
}: Readonly<{
  entry: AtlasEntry;
  /** The social feature: the sponsor's name links to the profile only while it is on. */
  social: boolean;
  /** Reads the entry again and shows it; resolves to it, or null when it cannot be read. */
  refresh: () => Promise<AtlasEntry | null>;
}>) {
  const access = useAccess();
  const identity = useIdentity();
  const pathname = usePathname();
  const session = useSession();
  const [reporting, setReporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const sponsor = entry.sponsor ?? null;
  const mine =
    sponsor !== null && identity.status === 'ready' && identity.identity.handle === sponsor.handle;
  const waiting = entry.orphaned && sponsor === null;

  // Once it is no longer offered, the panel stays only to say what just happened.
  if (!waiting && sponsor === null && problem === null && notice === null) {
    return null;
  }

  const sponsorIt = async () => {
    setBusy(true);
    setProblem(null);
    setNotice(null);
    const result = await sponsorEntry(entry.id);
    if (result.ok) {
      setNotice(S.entry.sponsored);
      await refresh();
    } else {
      const fresh = result.code === 'CONFLICT' ? await refresh() : null;
      setProblem(refusalMessage(result, fresh));
    }
    setBusy(false);
  };

  const endIt = async () => {
    setBusy(true);
    setProblem(null);
    const result = await endSponsorship(entry.id);
    setEnding(false);
    if (result.ok) {
      setNotice(S.end.done);
      await refresh();
    } else {
      setProblem(failureMessage(result));
    }
    setBusy(false);
  };

  return (
    <section
      aria-label={S.entry.section}
      className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line px-4 py-4"
    >
      <h2 className="m-0 font-semibold text-[1.125rem] text-fg">{S.entry.section}</h2>
      <div role="status" className="empty:hidden">
        {notice === null ? null : <Notice tone="success">{notice}</Notice>}
      </div>
      {sponsor === null ? null : <SponsorLine sponsor={sponsor} social={social} />}
      {sponsor === null || entry.sponsor_reflection == null ? null : (
        <figure className="m-0 flex flex-col gap-1 border-line border-s-2 ps-3">
          <figcaption className="text-[0.8125rem] text-fg-muted">
            {S.entry.reflectionOf} · {S.entry.reflectionNote}
          </figcaption>
          <p className="m-0 text-fg leading-[1.9]">{entry.sponsor_reflection}</p>
          {session.status === 'signed-in' && !mine && entry.sponsor_reflection_id != null ? (
            <>
              <Button
                variant="ghost"
                onClick={() => setReporting(true)}
                className="min-h-10 self-start px-3 text-[0.875rem]"
              >
                {S.entry.reportReflection}
              </Button>
              <ReportSheet
                open={reporting}
                onClose={() => setReporting(false)}
                targetType="sponsorship"
                targetId={entry.sponsor_reflection_id}
              />
            </>
          ) : null}
        </figure>
      )}
      {waiting ? (
        <>
          <p className="m-0 text-fg-soft leading-[1.85]">{S.entry.waitingLead}</p>
          {access === 'guest' ? (
            <p className="m-0 flex flex-wrap items-center gap-x-3 text-fg-soft">
              {S.entry.signIn}
              <Link
                href={signInHref(pathname)}
                className="font-medium text-link underline-offset-4 hover:underline"
              >
                {messages.community.signIn}
              </Link>
            </p>
          ) : null}
          {access === 'unverified' ? (
            <AccessNote access={access} guest="" unverified={S.entry.verify} />
          ) : null}
          {access === 'no-identity' ? (
            <div className="flex flex-col gap-3">
              <p className="m-0 font-semibold text-fg">{S.entry.identityFirst}</p>
              <IdentityForm />
            </div>
          ) : null}
          {access === 'member' ? (
            <Button disabled={busy} onClick={() => void sponsorIt()} className="self-start">
              {busy ? S.entry.acting : S.entry.action}
            </Button>
          ) : null}
        </>
      ) : null}
      {mine ? (
        <>
          <p className="m-0 text-fg-soft">{S.entry.mine}</p>
          <ReflectionForm entry={entry} refresh={refresh} />
          <Button variant="ghost" onClick={() => setEnding(true)} className="self-start">
            {S.end.action}
          </Button>
          <Sheet
            open={ending}
            onClose={() => setEnding(false)}
            title={S.end.title}
            description={S.end.lead}
          >
            <div className="flex flex-wrap gap-2.5 pb-2">
              <Button onClick={() => void endIt()} disabled={busy}>
                {busy ? S.end.ending : S.end.confirm}
              </Button>
              <Button variant="ghost" onClick={() => setEnding(false)}>
                {S.end.cancel}
              </Button>
            </div>
          </Sheet>
        </>
      ) : null}
      {problem === null ? null : (
        <div role="alert" className="flex flex-col items-start gap-2">
          <Notice tone="error">{problem}</Notice>
          {problem === S.refusal.identity ? (
            <Link
              href="/me#identity"
              className="font-medium text-link underline-offset-4 hover:underline"
            >
              {messages.community.comments.chooseIdentity}
            </Link>
          ) : null}
        </div>
      )}
    </section>
  );
}
