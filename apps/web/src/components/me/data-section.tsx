'use client';

import { type SyntheticEvent, useId, useRef, useState } from 'react';
import { type ConsentEntry, deleteAccount, exportAccount } from '@/account/profile';
import { setGuest } from '@/account/session';
import { DownloadIcon, TrashIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { formatWhen } from '@/lib/dates';
import { messages } from '@/messages';
import { MeSection, SubHeading } from './me-section';

const D = messages.pages.me.data;
const X = messages.pages.me.delete;
const EXPORT_FILE = 'tabsira-export.json';

/** Hands the visitor a file made in the page: nothing is uploaded or fetched for it. */
function saveFile(name: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function ExportData() {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle');
  const [failure, setFailure] = useState<string | null>(null);
  const download = async () => {
    setState('busy');
    setFailure(null);
    const result = await exportAccount();
    if (result.ok) {
      saveFile(EXPORT_FILE, `${JSON.stringify(result.data, null, 2)}\n`);
      setState('done');
    } else {
      setState('idle');
      setFailure(failureMessage(result));
    }
  };
  return (
    <div className="flex flex-col items-start gap-2">
      <p className="m-0 text-fg-soft text-sm">{D.exportHint}</p>
      <Button variant="secondary" onClick={download} disabled={state === 'busy'}>
        <DownloadIcon width="18" height="18" />
        {state === 'busy' ? D.exporting : D.export}
      </Button>
      <p role="status" className="m-0 text-fg-soft text-sm empty:hidden">
        {state === 'done' ? D.exported : null}
      </p>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </div>
  );
}

type History =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; entries: ConsentEntry[] }
  | { status: 'failed'; message: string };

/** The consents given and withdrawn, newest first, loaded the first time it is opened. */
function ConsentHistory() {
  const [history, setHistory] = useState<History>({ status: 'idle' });
  const onToggle = async (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (!event.currentTarget.open || history.status === 'loading' || history.status === 'ready') {
      return;
    }
    setHistory({ status: 'loading' });
    const result = await exportAccount();
    setHistory(
      result.ok
        ? { status: 'ready', entries: [...result.data.consents].reverse() }
        : { status: 'failed', message: failureMessage(result) }
    );
  };
  return (
    <details
      onToggle={onToggle}
      className="group rounded-[var(--radius-card)] border border-line bg-surface"
    >
      <summary className="flex min-h-12 cursor-pointer items-center px-4 font-semibold text-fg">
        {D.history}
      </summary>
      <div className="flex flex-col gap-2 px-4 pb-4" aria-live="polite">
        {history.status === 'loading' ? (
          <p className="m-0 text-fg-muted">{D.historyLoading}</p>
        ) : null}
        {history.status === 'failed' ? <Notice tone="error">{history.message}</Notice> : null}
        {history.status === 'ready' && history.entries.length === 0 ? (
          <p className="m-0 text-fg-muted">{D.historyEmpty}</p>
        ) : null}
        {history.status === 'ready' && history.entries.length > 0 ? (
          <ol className="m-0 flex list-none flex-col gap-2 p-0">
            {history.entries.map((entry) => (
              <li
                key={`${entry.kind}-${entry.created_at}`}
                className="flex flex-col gap-0.5 border-line border-b pb-2 last:border-b-0"
              >
                <span className="text-fg">
                  {D.kinds[entry.kind]}: {entry.granted ? D.granted : D.withdrawn}
                </span>{' '}
                <span className="text-fg-muted text-sm">
                  {formatWhen(entry.created_at)} · {D.textVersion('')}
                  <bdi dir="ltr">{entry.version}</bdi>
                </span>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </details>
  );
}

/**
 * Deleting the account, confirmed in the page itself (no browser dialog): the
 * consequences in words, the irreversible button apart from everything else
 * (Fitts: separate the destructive action), and the way back as the easy way out.
 */
function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const confirmId = useId();
  const confirmRef = useRef<HTMLHeadingElement>(null);
  const actionRef = useRef<HTMLButtonElement>(null);
  const [state, setState] = useState<'idle' | 'confirming' | 'deleting'>('idle');
  const [failure, setFailure] = useState<string | null>(null);

  const ask = () => {
    setState('confirming');
    requestAnimationFrame(() => confirmRef.current?.focus());
  };
  const cancel = () => {
    setState('idle');
    setFailure(null);
    requestAnimationFrame(() => actionRef.current?.focus());
  };
  const remove = async () => {
    setState('deleting');
    setFailure(null);
    const result = await deleteAccount();
    if (result.ok) {
      // The page becomes the guest's page; it says what happened at its top.
      onDeleted();
      setGuest();
    } else {
      setState('confirming');
      setFailure(failureMessage(result));
    }
  };

  return (
    <div className="flex flex-col items-start gap-3">
      <p className="m-0 text-fg-soft text-sm">{X.body}</p>
      {state === 'idle' ? (
        <Button
          ref={actionRef}
          variant="ghost"
          onClick={ask}
          className="border border-danger text-danger hover:text-danger"
        >
          <TrashIcon width="18" height="18" />
          {X.action}
        </Button>
      ) : (
        <section
          aria-labelledby={confirmId}
          className="flex w-full flex-col gap-3 rounded-[var(--radius-card)] border border-danger bg-surface p-4"
        >
          <h4
            ref={confirmRef}
            id={confirmId}
            tabIndex={-1}
            className="m-0 font-semibold text-danger text-lg outline-none"
          >
            {X.confirmTitle}
          </h4>
          <p className="m-0 text-fg leading-[1.85]">{X.confirmBody}</p>
          {failure === null ? null : (
            <div role="alert">
              <Notice tone="error">{failure}</Notice>
            </div>
          )}
          <div className="flex flex-wrap gap-2.5">
            <Button variant="secondary" onClick={cancel} disabled={state === 'deleting'}>
              {X.cancel}
            </Button>
            <Button
              variant="ghost"
              onClick={remove}
              disabled={state === 'deleting'}
              className="border border-danger text-danger hover:text-danger"
            >
              {state === 'deleting' ? X.deleting : X.confirm}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

/** The data section: take everything away (the export), see what was agreed to, or delete it all. */
export function DataSection({ onDeleted }: { onDeleted: () => void }) {
  return (
    <MeSection id="data" title={messages.pages.me.sections.data}>
      <ExportData />
      <ConsentHistory />
      <SubHeading>{X.title}</SubHeading>
      <DeleteAccount onDeleted={onDeleted} />
    </MeSection>
  );
}
