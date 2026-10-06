'use client';

import { type SubmitEvent, useEffect, useState } from 'react';
import { MoreIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { CheckboxField } from '@/components/ui/checkbox-field';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { TextArea } from '@/components/ui/text-area';
import { type Feedback, type FeedbackReason, rateInsight } from '@/lib/scan/api';
import { messages } from '@/messages';

const T = messages.insightPage.feedback;
/** The API's own bound (`FEEDBACK_NOTE_MAX`). */
export const NOTE_MAX = 300;
const REASONS = Object.keys(T.reasons) as FeedbackReason[];

export interface FeedbackState {
  saved: Feedback | null;
  open: boolean;
  /** The choice the sheet opens on: answering no opens it on not useful. */
  start: boolean | null;
  /** Rated during this visit: the line says thank you instead of what was chosen. */
  justSaved: boolean;
}

/**
 * The reader's rating of their insight, kept out of the way (plan 04.16): one
 * quiet line once the insight is done, and the small ⋯ button at the top for any
 * time. A yes is saved at once; a no opens the sheet for reasons and a note.
 * Nothing here is shown to anyone but the reader and the team.
 */
export function useFeedback(insightId: string, initial: Feedback | null) {
  const [state, setState] = useState<FeedbackState>({
    saved: initial,
    open: false,
    start: null,
    justSaved: false,
  });
  // The insight arrives after the first render: take its rating once it is there.
  useEffect(() => {
    if (initial !== null) {
      setState((now) => ({ ...now, saved: now.saved ?? initial }));
    }
  }, [initial]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // Every control that sends is disabled while `sending`, so one rating is in flight at a time.
  const send = async (helpful: boolean, reasons: FeedbackReason[] = [], note = '') => {
    setSending(true);
    setError(null);
    const result = await rateInsight(insightId, {
      helpful,
      reasons: helpful ? [] : reasons,
      note: note.trim() === '' ? null : note,
    });
    setSending(false);
    if (!result.ok) {
      setError(T.failed);
      return false;
    }
    setState({ saved: result.data, open: false, start: null, justSaved: true });
    return true;
  };

  return {
    state,
    error,
    sending,
    send,
    open: (start: boolean | null = null) => setState((now) => ({ ...now, open: true, start })),
    close: () => setState((now) => ({ ...now, open: false })),
  };
}

export type FeedbackControls = ReturnType<typeof useFeedback>;

/** The small button at the top of the insight: rate it, or say what went wrong, at any time. */
export function FeedbackMenuButton({ onOpen }: Readonly<{ onOpen: () => void }>) {
  return (
    <Button variant="icon" label={T.menu} onClick={onOpen} className="size-10 text-fg-muted">
      <MoreIcon className="size-5" />
    </Button>
  );
}

/** One quiet line under the done step: was it useful, yes or no, then a thank-you. */
export function FeedbackLine({ controls }: Readonly<{ controls: FeedbackControls }>) {
  const { state, error, sending, send, open } = controls;
  const saved = state.saved;
  if (saved !== null) {
    const rated = saved.helpful ? T.ratedHelpful : T.ratedNotHelpful;
    return (
      <p role="status" className="m-0 flex flex-wrap items-center gap-x-3 text-fg-muted text-sm">
        <span>{state.justSaved ? T.thanks : rated}</span>
        <button
          type="button"
          onClick={() => open(saved.helpful)}
          className="min-h-11 text-link underline underline-offset-4"
        >
          {T.change}
        </button>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <p className="m-0 flex flex-wrap items-center gap-x-3 text-fg-muted text-sm">
        <span>{T.question}</span>
        <button
          type="button"
          disabled={sending}
          onClick={() => void send(true)}
          className="min-h-11 px-1 text-link underline underline-offset-4"
        >
          {T.yes}
        </button>
        <button
          type="button"
          disabled={sending}
          onClick={() => open(false)}
          className="min-h-11 px-1 text-link underline underline-offset-4"
        >
          {T.no}
        </button>
      </p>
      <div role="alert">{error === null ? null : <Notice tone="error">{error}</Notice>}</div>
    </div>
  );
}

/** The sheet: useful or not, the reasons of a «not useful», and a short note. */
export function FeedbackSheet({ controls }: Readonly<{ controls: FeedbackControls }>) {
  const { state, error, sending, send, close } = controls;
  return (
    <Sheet open={state.open} onClose={close} title={T.title}>
      {state.open ? (
        <FeedbackForm
          // A new opening starts from what was saved, or from the choice that opened it.
          key={`${state.saved?.updated_at ?? 'new'}-${String(state.start)}`}
          saved={state.saved}
          start={state.start}
          error={error}
          sending={sending}
          onSend={send}
        />
      ) : null}
    </Sheet>
  );
}

interface FeedbackFormProps {
  saved: Feedback | null;
  start: boolean | null;
  error: string | null;
  sending: boolean;
  onSend: (helpful: boolean, reasons: FeedbackReason[], note: string) => Promise<boolean>;
}

function FeedbackForm({ saved, start, error, sending, onSend }: Readonly<FeedbackFormProps>) {
  const [helpful, setHelpful] = useState<boolean | null>(start ?? saved?.helpful ?? null);
  const [reasons, setReasons] = useState<FeedbackReason[]>(saved?.reasons ?? []);
  const [note, setNote] = useState(saved?.note ?? '');
  const tooLong = Array.from(note).length > NOTE_MAX;

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (helpful === null || tooLong) {
      return;
    }
    void onSend(helpful, reasons, note);
  };

  const toggle = (reason: FeedbackReason, on: boolean) =>
    setReasons((now) => (on ? [...now, reason] : now.filter((item) => item !== reason)));

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 pb-2" noValidate>
      <fieldset className="m-0 flex flex-wrap gap-2 border-0 p-0">
        <legend className="mb-2 font-medium text-[0.9375rem] text-fg">{T.choiceLegend}</legend>
        {[true, false].map((value) => (
          <Button
            key={String(value)}
            variant={helpful === value ? 'primary' : 'secondary'}
            aria-pressed={helpful === value}
            onClick={() => setHelpful(value)}
          >
            {value ? T.helpful : T.notHelpful}
          </Button>
        ))}
      </fieldset>
      {helpful === false ? (
        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-1 font-medium text-[0.9375rem] text-fg">{T.reasonsLegend}</legend>
          {REASONS.map((reason) => (
            <CheckboxField
              key={reason}
              label={T.reasons[reason]}
              checked={reasons.includes(reason)}
              onChange={(on) => toggle(reason, on)}
            />
          ))}
        </fieldset>
      ) : null}
      {helpful === null ? null : (
        <TextArea
          label={T.noteLabel}
          hint={T.noteHint}
          maxChars={NOTE_MAX}
          value={note}
          rows={3}
          onChange={(event) => setNote(event.target.value)}
        />
      )}
      <div role="alert">{error === null ? null : <Notice tone="error">{error}</Notice>}</div>
      <Button type="submit" disabled={helpful === null || tooLong || sending}>
        {T.send}
      </Button>
    </form>
  );
}
