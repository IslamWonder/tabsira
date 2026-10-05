'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { signInHref } from '@/account/links';
import { sponsorEntry } from '@/atlas/api';
import type { AtlasEntry } from '@/atlas/types';
import { IdentityForm } from '@/components/community/identity-section';
import { AccessNote } from '@/components/community/sheets';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import type { Failure } from '@/lib/api/result';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { profilePath } from '@/social/identity';

const S = messages.atlas.sponsor;

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
}: {
  sponsor: NonNullable<AtlasEntry['sponsor']>;
  social: boolean;
}) {
  const name = (
    <>
      {sponsor.public_name} <bdi dir="ltr">@{sponsor.handle}</bdi>
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

/**
 * Sponsoring on the entry's page (decision 60). An orphaned entry offers
 * the sponsor action to a verified member with a public identity, and to others the
 * missing step; a sponsored one names its sponsor and shows the published reflection.
 * Nothing here counts or rewards. The server judges every action; this only says why not.
 */
export function SponsorPanel({
  entry,
  social,
  refresh,
}: {
  entry: AtlasEntry;
  /** The social feature: the sponsor's name links to the profile only while it is on. */
  social: boolean;
  /** Reads the entry again and shows it; resolves to it, or null when it cannot be read. */
  refresh: () => Promise<AtlasEntry | null>;
}) {
  const access = useAccess();
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const sponsor = entry.sponsor ?? null;
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
