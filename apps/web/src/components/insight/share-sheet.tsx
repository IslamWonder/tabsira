'use client';

import Image from 'next/image';
import { useState } from 'react';
import { track } from '@/analytics/events';
import { Button, buttonClasses } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import type { Failure } from '@/lib/api/result';
import { publicInsightCardPath, publicInsightPath } from '@/lib/public-insight';
import type { Insight } from '@/lib/scan/api';
import { siteOrigin } from '@/lib/site';
import { messages } from '@/messages';
import type { PublishingState } from './use-insight';

const T = messages.share;

export interface ShareSheetProps {
  open: boolean;
  onClose: () => void;
  insight: Insight;
  publishing: PublishingState;
  onPublish: () => void;
  onWithdraw: () => void;
}

/** The public page's absolute address and the card the share sheet offers with it. */
export function shareLinks(insightId: string) {
  const origin = siteOrigin();
  return {
    url: new URL(publicInsightPath(insightId), origin).toString(),
    card: new URL(publicInsightCardPath(insightId), origin).toString(),
  };
}

export function publishFailureMessage(failure: Failure): string {
  if (failure.status === 409) {
    return T.failures.notPublishable;
  }
  if (failure.code === 'EMAIL_NOT_VERIFIED') {
    return T.failures.verify;
  }
  if (failure.status === 401) {
    return T.failures.signIn;
  }
  if (failure.status === 403 || failure.status === 404) {
    return T.failures.forbidden;
  }
  return T.failures.other;
}

/**
 * Sharing (master prompt v2 §18): the owner sees what the public page shows
 * before publishing (the preview v2 §18 asks for), publishes with one tap, then gets the
 * link to copy, the device's share sheet when it has one, the card to download,
 * and withdrawal at any time. Nothing is published without the tap.
 */
export function ShareSheet({
  open,
  onClose,
  insight,
  publishing,
  onPublish,
  onWithdraw,
}: ShareSheetProps) {
  const [copied, setCopied] = useState<'idle' | 'copied' | 'failed'>('idle');
  const saving = publishing.status === 'saving';
  const links = insight.published_at === null ? null : shareLinks(insight.id);
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied('copied');
      track('share', { method: 'link', kind: 'insight' });
    } catch {
      setCopied('failed');
    }
  };

  const share = async (url: string) => {
    try {
      await navigator.share({ title: insight.title, text: T.shareText(insight.title), url });
      track('share', { method: 'system', kind: 'insight' });
    } catch {
      // The person closed the sheet, or the device refused: the link stays in the field.
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={T.title} description={T.description}>
      <div className="flex flex-col gap-4">
        <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.8]">{T.whatShows}</p>
        {publishing.failure === undefined ? null : (
          <div role="alert">
            <Notice tone="error">{publishFailureMessage(publishing.failure)}</Notice>
          </div>
        )}
        {links === null ? (
          <Button variant="primary" onClick={onPublish} disabled={saving}>
            {saving ? T.publishing : T.publish}
          </Button>
        ) : (
          <>
            <p role="status" className="m-0 font-semibold text-fg">
              {T.published}
            </p>
            <label className="flex flex-col gap-1 text-fg-soft text-sm">
              {T.link}
              <input
                readOnly
                value={links.url}
                dir="ltr"
                className="min-h-11 rounded-[var(--radius-card)] border border-line bg-surface px-3 text-fg text-sm"
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
            <Image
              src={links.card}
              alt={T.cardAlt}
              width={1200}
              height={630}
              // Drawn on request by our own route; the optimiser would only add a hop.
              unoptimized
              className="h-auto w-full rounded-[var(--radius-card)] border border-line"
            />
            <div className="flex flex-wrap gap-2.5">
              {canShare ? (
                <Button variant="primary" onClick={() => share(links.url)}>
                  {T.system}
                </Button>
              ) : null}
              <Button variant="secondary" onClick={() => copy(links.url)}>
                {T.copy}
              </Button>
              <a
                href={links.card}
                download={`tabsira-${insight.id}.png`}
                className={buttonClasses('secondary')}
                onClick={() => track('share', { method: 'card', kind: 'insight' })}
              >
                {T.download}
              </a>
            </div>
            <p role="status" className="m-0 min-h-5 text-fg-soft text-sm">
              {copied === 'copied' ? T.copied : copied === 'failed' ? T.copyFailed : ''}
            </p>
            <Button variant="ghost" onClick={onWithdraw} disabled={saving}>
              {saving ? T.withdrawing : T.withdraw}
            </Button>
          </>
        )}
      </div>
    </Sheet>
  );
}
