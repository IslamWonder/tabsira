'use client';

import { useEffect, useRef } from 'react';
import { celebrate } from '@/components/fx/celebrate';
import { CheckIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export type DoneStatus = 'idle' | 'saving' | 'done';

export interface DoneButtonProps {
  status?: DoneStatus;
  onDone: () => void;
  className?: string;
}

/**
 * the done button, the one primary action at the end of an insight (Fitts: the widest
 * target in the thumb zone; Von Restorff: the only glowing fill). The burst of
 * light and the banner "meaning discovered" come when the save has succeeded, not
 * on the tap (tajriba §3.5: announce success after it is confirmed), so the
 * high point is a true one (Peak-End rule). While saving, a second tap cannot
 * record twice.
 */
export function DoneButton({ status = 'idle', onDone, className }: DoneButtonProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const previous = useRef(status);

  useEffect(() => {
    if (status === 'done' && previous.current !== 'done') {
      celebrate(ref.current as HTMLButtonElement);
    }
    previous.current = status;
  }, [status]);

  return (
    <Button
      ref={ref}
      size="lg"
      onClick={onDone}
      disabled={status !== 'idle'}
      aria-busy={status === 'saving'}
      className={cx('w-full', className)}
    >
      {status === 'done' ? <CheckIcon width="22" height="22" /> : null}
      {messages.insight.done}
    </Button>
  );
}
