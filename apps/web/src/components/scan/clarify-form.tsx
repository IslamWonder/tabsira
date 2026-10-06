'use client';

import { type FormEvent, useState } from 'react';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import type { Failure } from '@/lib/api/result';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { messages } from '@/messages';

const T = messages.scan.clarify;

export interface ClarifyFormProps {
  /** The one question the scan asked, in the API's words. */
  question: string;
  /** Sends the answer; null when accepted, else why not. */
  onAnswer: (answer: string) => Promise<Failure | null>;
  acting: boolean;
}

/**
 * The single question that changes the result (tajriba S08, LUX-05): shown
 * as the API asked it, answered in a few words, with nothing else to decide.
 * A refused answer says why and keeps what was typed.
 */
export function ClarifyForm({ question, onAnswer, acting }: Readonly<ClarifyFormProps>) {
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (acting) {
      return;
    }
    const text = answer.trim();
    if (text === '') {
      setError(T.empty);
      return;
    }
    setError(null);
    const failure = await onAnswer(text);
    if (failure !== null) {
      setError(journeyFailureMessage(failure));
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <h2 className="m-0 font-semibold text-subheading text-fg">{T.title}</h2>
      <p className="m-0 font-medium text-[1.0625rem] text-fg leading-[1.8]">{question}</p>
      <TextField
        label={T.label}
        hint={T.hint}
        value={answer}
        maxLength={300}
        error={error}
        onChange={(event) => setAnswer(event.target.value)}
      />
      <div>
        <Button type="submit" disabled={acting} aria-busy={acting}>
          {acting ? T.submitting : T.submit}
        </Button>
      </div>
    </form>
  );
}
