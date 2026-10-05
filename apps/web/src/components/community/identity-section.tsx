'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useState } from 'react';
import { useSession } from '@/account/session';
import { MeSection, SubHeading } from '@/components/me/me-section';
import { SaveStatus, useSaveState } from '@/components/me/save-status';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { listBlocks, putIdentity, setBlock } from '@/social/api';
import { cleanHandle, HANDLE_MAX, handleProblem, profilePath } from '@/social/identity';
import { hasIdentity, setIdentity, useIdentity } from '@/social/identity-store';
import type { Member } from '@/social/types';

const I = messages.community.identity;
const B = messages.community.block;

/** Choose or change the handle; the full name is shown only by the consent of «ملفي» (decision 63). */
export function IdentityForm() {
  const identity = useIdentity();
  const [handle, setHandle] = useState('');
  const [touched, setTouched] = useState(false);
  const [taken, setTaken] = useState(false);
  const save = useSaveState();

  const current = hasIdentity(identity) ? identity.identity : null;
  useEffect(() => {
    if (current !== null) {
      setHandle(current.handle);
    }
  }, [current]);

  const handleError = touched ? handleProblem(handle) : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    setTaken(false);
    if (handleProblem(handle) !== null) {
      return;
    }
    await save.run(async () => {
      const result = await putIdentity(cleanHandle(handle));
      if (result.ok) {
        setIdentity(result.data);
        return null;
      }
      if (result.code === 'HANDLE_TAKEN') {
        setTaken(true);
        return I.taken;
      }
      if (result.code === 'VALIDATION_ERROR') {
        return I.problems.handleShape;
      }
      return failureMessage(result);
    });
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      {current === null ? <p className="m-0 text-fg-soft text-sm">{I.none}</p> : null}
      <TextField
        label={I.handle}
        hint={I.handleHint}
        value={handle}
        onChange={(event) => setHandle(event.target.value)}
        error={taken ? I.taken : handleError}
        maxLength={HANDLE_MAX + 2}
        autoComplete="off"
        spellCheck={false}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" disabled={save.busy}>
          {save.busy ? I.saving : I.save}
        </Button>
        {current === null ? null : (
          <Link
            href={profilePath(current.handle)}
            className="text-link underline-offset-4 hover:underline"
          >
            {I.page}
          </Link>
        )}
      </div>
      <SaveStatus state={save.state} />
    </form>
  );
}

/** The members the person blocked, by handle and public name only, with a way to lift each block. */
export function BlocksList() {
  const [load, setLoad] = useState<
    { kind: 'loading' | 'failed' } | { kind: 'ready'; members: Member[] }
  >({
    kind: 'loading',
  });
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void listBlocks().then((result) =>
      setLoad(result.ok ? { kind: 'ready', members: result.data } : { kind: 'failed' })
    );
  }, []);

  const unblock = async (member: Member) => {
    setFailure(null);
    const result = await setBlock(member.handle, false);
    if (result.ok) {
      /* v8 ignore next 7: a block is lifted only from the ready list, so `current` is always ready; the other arm satisfies the union */
      setLoad((current) =>
        current.kind === 'ready'
          ? {
              kind: 'ready',
              members: current.members.filter((item) => item.handle !== member.handle),
            }
          : current
      );
      setNotice(B.unblocked);
    } else {
      setFailure(failureMessage(result));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <SubHeading>{B.listTitle}</SubHeading>
      <p className="m-0 text-fg-muted text-sm leading-[1.8]">{B.listHint}</p>
      {load.kind === 'loading' ? (
        <p role="status" className="m-0 text-fg-muted text-sm">
          {B.listLoading}
        </p>
      ) : null}
      {load.kind === 'failed' ? (
        <div role="alert">
          <Notice tone="error">{B.listFailed}</Notice>
        </div>
      ) : null}
      {load.kind === 'ready' && load.members.length === 0 ? (
        <p className="m-0 text-fg-soft text-sm">{B.listEmpty}</p>
      ) : null}
      {load.kind === 'ready' && load.members.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {load.members.map((member) => (
            <li key={member.handle} className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex flex-wrap items-baseline gap-x-2">
                {member.public_name === null ? null : (
                  <span className="font-medium text-fg">{member.public_name}</span>
                )}
                <bdi className="text-[0.875rem] text-fg-muted">@{member.handle}</bdi>
              </span>
              <Button variant="ghost" onClick={() => void unblock(member)}>
                {B.unblock}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <p role="status" className="m-0 text-fg-soft text-sm empty:hidden">
        {notice}
      </p>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </div>
  );
}

/** The public-identity part of the profile page: the identity form, and the blocks the person holds. */
export function IdentitySection() {
  const session = useSession();
  if (session.status !== 'signed-in') {
    return null;
  }
  return (
    <MeSection id="identity" title={I.title} description={I.description}>
      {session.user.email_verified ? (
        <IdentityForm />
      ) : (
        <p className="m-0 text-fg-soft leading-[1.85]">{I.verify}</p>
      )}
      <BlocksList />
    </MeSection>
  );
}
