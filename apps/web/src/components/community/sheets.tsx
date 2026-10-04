'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { type FormEvent, useState } from 'react';
import { signInHref } from '@/account/links';
import { Button } from '@/components/ui/button';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { TextArea } from '@/components/ui/text-area';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { type Access, useAccess } from '@/social/access';
import { fileReport, setBlock, withdrawPost } from '@/social/api';
import {
  REPORT_DETAILS_MAX,
  REPORT_REASONS,
  type ReportReason,
  type ReportTarget,
} from '@/social/types';

const C = messages.community;

/**
 * What a guest or an unverified account is told before an action the API
 * would refuse: the missing step, and the way to it (tajriba §8: a permission
 * not granted gets an understandable alternative, never a penalty).
 */
export function AccessNote({
  access,
  guest,
  unverified,
  identity,
}: {
  access: Access;
  guest: string;
  unverified: string;
  /** When the action also needs a public identity (posting, commenting). */
  identity?: string;
}) {
  const pathname = usePathname();
  if (access === 'guest') {
    return (
      <p className="m-0 flex flex-wrap items-center gap-x-3 text-fg-soft">
        {guest}
        <Link
          href={signInHref(pathname)}
          className="font-medium text-link underline-offset-4 hover:underline"
        >
          {C.signIn}
        </Link>
      </p>
    );
  }
  if (access === 'unverified') {
    return <p className="m-0 text-fg-soft">{unverified}</p>;
  }
  if (access === 'no-identity' && identity !== undefined) {
    return (
      <p className="m-0 flex flex-wrap items-center gap-x-3 text-fg-soft">
        {identity}
        <Link
          href="/me#identity"
          className="font-medium text-link underline-offset-4 hover:underline"
        >
          {C.comments.chooseIdentity}
        </Link>
      </p>
    );
  }
  return null;
}

export interface ReportSheetProps {
  open: boolean;
  onClose: () => void;
  targetType: ReportTarget;
  targetId: string;
}

/** Report a post or a comment with one of the API's reasons; the report reaches the moderators alone. */
export function ReportSheet({ open, onClose, targetType, targetId }: ReportSheetProps) {
  const access = useAccess();
  const [reason, setReason] = useState<ReportReason>('abuse');
  const [details, setDetails] = useState('');
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle');
  const [failure, setFailure] = useState<string | null>(null);
  const canSend = access === 'member' || access === 'no-identity';

  const send = async (event: FormEvent) => {
    event.preventDefault();
    setState('sending');
    setFailure(null);
    const result = await fileReport({
      targetType,
      targetId,
      reason,
      details: details.trim() === '' ? null : details.trim(),
    });
    if (result.ok) {
      setState('sent');
    } else {
      setState('idle');
      setFailure(failureMessage(result));
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={C.report.title} description={C.report.lead}>
      {state === 'sent' ? (
        <div role="status" className="pb-2">
          <Notice tone="success">{C.report.sent}</Notice>
        </div>
      ) : (
        <form onSubmit={send} className="flex flex-col gap-5 pb-2">
          <ChoiceGroup
            legend={C.report.reason}
            options={REPORT_REASONS.map((value) => ({ value, label: C.report.reasons[value] }))}
            value={reason}
            onChange={setReason}
            disabled={!canSend}
          />
          <TextArea
            label={C.report.details}
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            maxChars={REPORT_DETAILS_MAX}
            rows={3}
            disabled={!canSend}
          />
          <AccessNote access={access} guest={C.report.signIn} unverified={C.report.verify} />
          {failure === null ? null : (
            <div role="alert">
              <Notice tone="error">{failure}</Notice>
            </div>
          )}
          <Button
            type="submit"
            size="lg"
            disabled={
              !canSend || state === 'sending' || Array.from(details).length > REPORT_DETAILS_MAX
            }
          >
            {state === 'sending' ? C.report.sending : C.report.send}
          </Button>
        </form>
      )}
    </Sheet>
  );
}

export interface BlockSheetProps {
  open: boolean;
  onClose: () => void;
  handle: string;
  publicName: string;
  /** The block stands: the member's posts and comments leave the viewer's lists. */
  onBlocked: () => void;
}

/** Confirm a block, which hides each of the two from the other everywhere and ends their follows. */
export function BlockSheet({ open, onClose, handle, publicName, onBlocked }: BlockSheetProps) {
  const access = useAccess();
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle');
  const [failure, setFailure] = useState<string | null>(null);
  const block = async () => {
    setState('busy');
    setFailure(null);
    const result = await setBlock(handle, true);
    if (result.ok) {
      setState('done');
      onBlocked();
    } else {
      setState('idle');
      setFailure(failureMessage(result));
    }
  };
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={C.block.title(publicName)}
      description={C.block.lead}
    >
      <div className="flex flex-col gap-4 pb-2">
        {state === 'done' ? (
          <div role="status">
            <Notice tone="success">{C.block.blocked}</Notice>
          </div>
        ) : null}
        {failure === null ? null : (
          <div role="alert">
            <Notice tone="error">{failure}</Notice>
          </div>
        )}
        <AccessNote access={access} guest={C.block.signIn} unverified="" />
        {state === 'done' ? null : (
          <div className="flex flex-wrap gap-2.5">
            <Button
              onClick={block}
              disabled={state === 'busy' || access === 'guest' || access === 'unknown'}
            >
              {state === 'busy' ? C.block.blocking : C.block.confirm}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              {C.block.cancel}
            </Button>
          </div>
        )}
      </div>
    </Sheet>
  );
}

export interface WithdrawSheetProps {
  open: boolean;
  onClose: () => void;
  postId: string;
  /** The post is gone: its address answers 410 from now on. */
  onWithdrawn: () => void;
}

/** The author takes a post down, draft or published; its content is erased at once. */
export function WithdrawSheet({ open, onClose, postId, onWithdrawn }: WithdrawSheetProps) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const withdraw = async () => {
    setBusy(true);
    setFailure(null);
    const result = await withdrawPost(postId);
    setBusy(false);
    if (result.ok) {
      onWithdrawn();
    } else {
      setFailure(failureMessage(result));
    }
  };
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={C.publish.withdrawTitle}
      description={C.publish.withdrawLead}
    >
      <div className="flex flex-col gap-4 pb-2">
        {failure === null ? null : (
          <div role="alert">
            <Notice tone="error">{failure}</Notice>
          </div>
        )}
        <div className="flex flex-wrap gap-2.5">
          <Button onClick={withdraw} disabled={busy}>
            {busy ? C.publish.withdrawing : C.publish.withdrawConfirm}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            {C.block.cancel}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
