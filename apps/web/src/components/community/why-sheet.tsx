'use client';

import Link from 'next/link';
import { Sheet } from '@/components/ui/sheet';
import { messages } from '@/messages';
import type { Why } from '@/social/types';

const W = messages.community.why;

/**
 * Why this: the one reason the API gave for this item, then the four
 * inputs of the for-you ranking as the reader is told them (docs/SOCIAL_NETWORK.md
 * «How the for-you feed ranks»): no model, nothing from the profile, and a way to switch
 * personalisation off.
 */
export function WhySheet({ why, open, onClose }: { why: Why; open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} onClose={onClose} title={W.title}>
      <div className="flex flex-col gap-5 pb-2">
        <div className="flex flex-col gap-1 rounded-[var(--radius-card)] bg-[var(--chip-primary-bg)] px-4 py-3">
          <p className="m-0 text-[0.8125rem] text-fg-muted">{W.reason}</p>
          <p className="m-0 font-semibold text-[var(--chip-primary-fg)]">{why.text}</p>
        </div>
        <p className="m-0 text-fg leading-[1.85]">{W.lead}</p>
        <ul className="m-0 flex list-disc flex-col gap-1.5 ps-5 text-fg-soft leading-[1.8]">
          {W.inputs.map((input) => (
            <li key={input}>{input}</li>
          ))}
        </ul>
        <p className="m-0 text-fg-soft text-sm leading-[1.8]">{W.never}</p>
        <p className="m-0 text-fg-soft text-sm leading-[1.8]">
          {W.personalisation}{' '}
          <Link href="/me#settings" className="text-link underline-offset-4 hover:underline">
            {W.settings}
          </Link>
        </p>
      </div>
    </Sheet>
  );
}
