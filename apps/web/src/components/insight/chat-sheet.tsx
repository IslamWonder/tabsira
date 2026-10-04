'use client';

import { type FormEvent, useId, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import type { Failure } from '@/lib/api/result';
import type { Insight } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { messages } from '@/messages';
import { DisclosureLine } from './disclosure-line';

const T = messages.insightPage.chat;
/** The API's limit of a question (apps/api/src/schemas/insight.py). */
const MAX_QUESTION = 500;

export interface ChatSheetProps {
  open: boolean;
  onClose: () => void;
  insightTitle: string;
  chat: Insight['chat'];
  /** Sends one question with its key; null when answered, else why not. */
  onAsk: (message: string, key: string) => Promise<Failure | null>;
}

/** A failure that asking again, with the same key, may mend: nothing answered, or our side broke. */
function mayRetry(failure: Failure): boolean {
  return failure.status === 0 || failure.status >= 500;
}

/**
 * The chat of one insight (v2 §14): three questions at most, and the sheet
 * always says how many are used. A question that fails keeps its key, so
 * sending it again is answered and counted once; a question the API refused
 * gets a new key when it is changed. The AI disclosure stays in view
 * (master prompt §12), and the title of the insight is the sheet's own
 * description, so the reader knows what they are asking about (Working memory).
 */
export function ChatSheet({ open, onClose, insightTitle, chat, onAsk }: ChatSheetProps) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const key = useRef<string | null>(null);
  const fieldId = useId();
  const errorId = useId();
  const canAsk = chat.enabled && chat.remaining > 0;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sending) {
      return;
    }
    const question = draft.trim();
    if (question === '') {
      setError(T.empty);
      return;
    }
    key.current ??= crypto.randomUUID();
    setError(null);
    setSending(true);
    const failure = await onAsk(question, key.current);
    setSending(false);
    if (failure === null) {
      key.current = null;
      setDraft('');
      return;
    }
    if (!mayRetry(failure)) {
      key.current = null;
    }
    setError(journeyFailureMessage(failure));
  };

  return (
    <Sheet open={open} onClose={onClose} title={T.title} description={insightTitle}>
      <div className="flex flex-col gap-4 pb-2">
        <p role="status" className="m-0 font-medium text-[0.9375rem] text-fg-soft">
          {T.used(chat.used, chat.limit)}
        </p>

        {chat.messages.length === 0 ? (
          <p className="m-0 text-fg-muted text-sm">{T.emptyState}</p>
        ) : (
          <ol className="m-0 flex list-none flex-col gap-4 p-0" aria-label={T.remaining}>
            {chat.messages.map((message) => (
              <li key={message.answered_at} className="flex flex-col gap-2">
                <p className="m-0 rounded-[var(--radius-card)] bg-surface px-4 py-2.5 text-fg leading-[1.8]">
                  <strong className="font-medium text-fg-soft text-sm">{T.asked}</strong>
                  <br />
                  {message.question}
                </p>
                <p className="m-0 whitespace-pre-wrap px-1 text-fg leading-[1.9]">
                  <strong className="font-medium text-fg-soft text-sm">{T.answered}</strong>
                  <br />
                  {message.answer}
                </p>
              </li>
            ))}
          </ol>
        )}

        {chat.enabled ? null : <Notice tone="info">{T.disabled}</Notice>}
        {chat.enabled && chat.remaining === 0 ? (
          <div role="status">
            <Notice tone="info">{T.limit}</Notice>
          </div>
        ) : null}

        {canAsk ? (
          <form onSubmit={submit} className="flex flex-col gap-2" noValidate>
            <label htmlFor={fieldId} className="font-medium text-[0.9375rem] text-fg">
              {T.label}
            </label>
            <p className="m-0 text-fg-muted text-sm">{T.hint}</p>
            <textarea
              id={fieldId}
              value={draft}
              maxLength={MAX_QUESTION}
              rows={3}
              onChange={(event) => setDraft(event.target.value)}
              aria-invalid={error === T.empty}
              aria-describedby={error === null ? undefined : errorId}
              className="min-h-24 rounded-[var(--radius-card)] border border-line bg-surface px-3 py-2 text-base text-fg leading-[1.8]"
            />
            <p id={errorId} role="alert" className="m-0 text-danger text-sm empty:hidden">
              {error}
            </p>
            <Button type="submit" disabled={sending} aria-busy={sending}>
              {sending ? T.sending : T.send}
            </Button>
          </form>
        ) : null}

        <DisclosureLine />
      </div>
    </Sheet>
  );
}
