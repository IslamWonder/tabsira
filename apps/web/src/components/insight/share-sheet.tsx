'use client';

import type { Route } from 'next';
import { useState } from 'react';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice, type NoticeTone } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import type { Failure } from '@/lib/api/result';
import { publicInsightPath } from '@/lib/public-insight';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { shareLink } from '@/lib/share-link';
import { siteOrigin } from '@/lib/site';
import { messages } from '@/messages';
import { publishInsight, withdrawInsight } from './publication';

const T = messages.sharing;

interface Said {
  tone: NoticeTone;
  text: string;
}

export interface ShareSheetProps {
  open: boolean;
  onClose: () => void;
  insightId: string;
  insightTitle: string;
  /** Whether the insight is public when the screen loads: the owner's own `published_at`. */
  published: boolean;
  /** The other publishing surfaces whose feature is on (read by the server): the atlas and the network. */
  publishTo?: PublishTargets;
}

export interface PublishTargets {
  atlas: boolean;
  community: boolean;
}

export const NO_TARGETS: PublishTargets = { atlas: false, community: false };

/** The page's address on this site, from the path the API names or, for an insight already public, the known one. */
function addressOf(path: string): string {
  return new URL(path, siteOrigin()).toString();
}

function refusal(failure: Failure): string {
  if (failure.status !== 409) {
    return journeyFailureMessage(failure);
  }
  if (failure.code === 'UNDER_13_CANNOT_PUBLISH') {
    return T.notForUnder13;
  }
  return failure.code === 'INSIGHT_NOT_PUBLISHABLE'
    ? T.notPublishable
    : journeyFailureMessage(failure);
}

/**
 * Sharing an insight (task 09.3): before the first publication the sheet says,
 * in one paragraph, what becomes public; the publish-and-share button publishes (a verified
 * owner's call, idempotent) and then hands the public address to the system's
 * share dialog, or copies it; while the insight is public its card image can be
 * downloaded as a file (v2 §18); the withdraw button takes the page down at once. The
 * API's own refusal (a sensitive scene, nothing to show from the store) is
 * said in Arabic, in words that name what to change.
 */
export function ShareSheet({
  open,
  onClose,
  insightId,
  insightTitle,
  published,
  publishTo = NO_TARGETS,
}: Readonly<ShareSheetProps>) {
  const [isPublic, setIsPublic] = useState(published);
  const [link, setLink] = useState<string | null>(
    published ? addressOf(publicInsightPath(insightId)) : null
  );
  const [working, setWorking] = useState(false);
  const [said, setSaid] = useState<Said | null>(null);

  const shareKnown = async (address: string) => {
    setWorking(true);
    setSaid(await shareLink(insightTitle, address));
    setWorking(false);
  };

  const publishAndShare = async () => {
    setWorking(true);
    setSaid(null);
    const result = await publishInsight(insightId);
    if (!result.ok) {
      setSaid({ tone: 'error', text: refusal(result) });
      setWorking(false);
      return;
    }
    // The API names the page's path; without it there is no address to hand out.
    if (result.data.path === null) {
      setSaid({ tone: 'error', text: messages.errors.server });
      setWorking(false);
      return;
    }
    const address = addressOf(result.data.path);
    setIsPublic(true);
    setLink(address);
    setSaid(await shareLink(insightTitle, address));
    setWorking(false);
  };

  const withdraw = async () => {
    setWorking(true);
    setSaid(null);
    const result = await withdrawInsight(insightId);
    setWorking(false);
    if (!result.ok) {
      setSaid({ tone: 'error', text: journeyFailureMessage(result) });
      return;
    }
    setIsPublic(false);
    setLink(null);
    setSaid({ tone: 'success', text: T.withdrawn });
  };

  const idleLabel = isPublic ? T.share : T.publishAndShare;
  return (
    <Sheet open={open} onClose={onClose} title={T.title} description={insightTitle}>
      <div className="flex flex-col gap-4 pb-2">
        <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.9]">
          {isPublic ? T.publicNow : T.whatBecomesPublic}
        </p>
        {link === null ? null : (
          <p className="m-0 flex flex-col gap-1 text-sm">
            <span className="font-medium text-fg-soft">{T.linkLabel}</span>
            <span dir="ltr" className="select-all break-all text-link">
              {link}
            </span>
          </p>
        )}
        <div role="status">
          {said === null || said.tone === 'error' ? null : (
            <Notice tone={said.tone}>{said.text}</Notice>
          )}
        </div>
        <div role="alert">
          {said?.tone === 'error' ? <Notice tone="error">{said.text}</Notice> : null}
        </div>
        <Button
          onClick={() => {
            if (isPublic && link !== null) {
              void shareKnown(link);
            } else {
              void publishAndShare();
            }
          }}
          disabled={working}
          aria-busy={working}
        >
          {working ? T.working : idleLabel}
        </Button>
        {isPublic ? (
          <Button variant="ghost" onClick={withdraw} disabled={working}>
            {T.withdraw}
          </Button>
        ) : null}
        {publishTo.atlas || publishTo.community ? (
          // Extension §2.3–2.4: the map and the network are offered inside sharing, each a separate
          // choice that opens its own preview; neither is switched on by the other.
          <section
            aria-label={T.moreWays}
            className="flex flex-col gap-2 border-line border-t pt-4"
          >
            <h3 className="m-0 font-semibold text-[0.9375rem] text-fg-soft">{T.moreWays}</h3>
            <div className="flex flex-wrap gap-2">
              {publishTo.atlas ? (
                <LinkButton
                  href={`/atlas/publish?insight=${insightId}` as Route}
                  variant="secondary"
                >
                  {T.publishMap}
                </LinkButton>
              ) : null}
              {publishTo.community ? (
                <LinkButton
                  href={`/community/publish?insight=${insightId}` as Route}
                  variant="secondary"
                >
                  {T.publishCommunity}
                </LinkButton>
              ) : null}
            </div>
            <p className="m-0 text-[0.8125rem] text-fg-muted leading-[1.8]">{T.publishSeparate}</p>
          </section>
        ) : null}
      </div>
    </Sheet>
  );
}
