'use client';

import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { useSession } from '@/account/session';
import { StatusScreen } from '@/components/app/status-screen';
import { ReadingLayout } from '@/components/layout/layouts';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import type { Insight } from '@/lib/scan/api';
import { journeyFailureMessage } from '@/lib/scan/failure';
import { signUpHref } from '@/lib/scan/gate';
import { centre } from '@/lib/scan/spans';
import { messages } from '@/messages';
import { ChatSheet } from './chat-sheet';
import { CompletionPanel, type ShareOption } from './completion-panel';
import { DisclosureLine } from './disclosure-line';
import { EngineLabel } from './engine-label';
import { ExplanationSections } from './explanation-sections';
import { InsightEvidence } from './insight-evidence';
import {
  InsightActions,
  InsightHeader,
  InsightPhoto,
  InsightTools,
  SeenNote,
} from './insight-frame';
import { PhotoPlaceholder } from './photo-placeholder';
import { NO_TARGETS, type PublishTargets, ShareSheet } from './share-sheet';
import { StepCard } from './step-card';
import { type PhotoView, useInsight } from './use-insight';
import { WhySheet } from './why-sheet';

const T = messages.insightPage;

function backTo(insight: Insight): Route {
  return (insight.scan_id === null ? '/' : `/scan/${insight.scan_id}`) as Route;
}

function Photo({
  view,
  insight,
  backHref,
}: {
  view: PhotoView | null;
  insight: Insight;
  backHref: Route;
}) {
  if (view === null) {
    return <PhotoPlaceholder note={T.loading} backHref={backHref} />;
  }
  if (view.kind === 'photo') {
    return (
      <InsightPhoto
        src={view.src}
        alt={insight.origin === 'tutorial' ? messages.scene.example.alt : T.photoAlt}
        width={view.width}
        height={view.height}
        focus={
          insight.anchor === null ? undefined : { ...centre(insight.anchor), title: insight.title }
        }
        backHref={backHref}
        unoptimized={view.unoptimized}
      />
    );
  }
  const notes = { sensitive: T.photoSensitive, gone: T.photoGone, none: T.photoNone } as const;
  return <PhotoPlaceholder note={notes[view.kind]} backHref={backHref} />;
}

/**
 * The insight (tajriba S02, §6): title and glimpse, what the photo shows, the
 * Quran and the Sunnah exactly as the API returns them, the platform's
 * explanation apart from them, the why-this sheet, the chat, the small step, and
 * the one primary the done action in the thumb zone. The photo stays beside or above the
 * text. What the API labels (a prepared example, a simulation, a relation, the
 * step's kind) is shown as it labels it.
 */
export function InsightScreen({
  insightId,
  publishTo = NO_TARGETS,
}: {
  insightId: string;
  /** FEATURE_ATLAS and FEATURE_SOCIAL, read by the server: the other ways to publish inside sharing. */
  publishTo?: PublishTargets;
}) {
  const controls = useInsight(insightId);
  const { load, photo, step, finish } = controls;
  const [whyOpen, setWhyOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const session = useSession();
  const router = useRouter();

  if (load.phase === 'loading') {
    return (
      <p role="status" className="px-6 py-16 text-center text-fg-soft">
        {T.loading}
      </p>
    );
  }
  if (load.phase === 'lost') {
    return (
      <StatusScreen
        emblem="logo"
        title={T.metaTitle}
        description={journeyFailureMessage(load.failure)}
        className="py-12"
      >
        <div className="flex flex-wrap justify-center gap-2.5">
          <Button variant="secondary" onClick={controls.reload}>
            {T.retry}
          </Button>
          <LinkButton href="/" variant="ghost">
            {messages.scan.another}
          </LinkButton>
        </div>
      </StatusScreen>
    );
  }

  const { insight } = load;
  const backHref = backTo(insight);
  const seen = insight.explanation.find((part) => part.section === 'seen');
  const { chat } = insight;
  // A guest's own scan has no chat: it asks for an account, and the insight moves into it (decision 63).
  const discuss = () => {
    if (session.status === 'guest' && insight.engine === 'pipeline') {
      router.push(signUpHref(`/insight/${insight.id}` as Route, 'chat'));
    } else {
      setChatOpen(true);
    }
  };
  // The API publishes only a signed-in owner's insight from the real analysis; offer sharing only then.
  const canShare = session.status === 'signed-in' && insight.engine === 'pipeline';
  const share: ShareOption = canShare
    ? { kind: 'open', onOpen: () => setShareOpen(true) }
    : {
        kind: 'blocked',
        reason:
          insight.engine !== 'pipeline'
            ? messages.completion.shareExample
            : messages.completion.shareSignIn,
      };

  return (
    <>
      <ReadingLayout
        media={<Photo view={photo} insight={insight} backHref={backHref} />}
        footer={
          <div className="flex flex-col gap-2">
            {finish.error === undefined ? null : (
              <div role="alert">
                <Notice tone="error">{finish.error}</Notice>
              </div>
            )}
            <InsightActions
              status={finish.status}
              onDone={() => {
                void controls.complete();
              }}
              onShare={canShare ? () => setShareOpen(true) : undefined}
            />
          </div>
        }
      >
        <EngineLabel engine={insight.engine} label={insight.label} />
        <InsightHeader
          backHref={backHref}
          chips={<Chip>{insight.relation_label}</Chip>}
          title={insight.title}
          glimpse={insight.glimpse}
        />
        {seen === undefined ? null : <SeenNote text={seen.text} />}
        <InsightEvidence insight={insight} />
        <ExplanationSections tag={insight.explanation_tag} parts={insight.explanation} />
        <InsightTools
          onWhy={() => setWhyOpen(true)}
          onDiscuss={discuss}
          discussNote={messages.insightPage.chat.used(chat.used, chat.limit)}
        />
        {insight.small_step === null ? null : (
          <StepCard
            body={insight.small_step.text}
            label={insight.small_step.label}
            confirmLabel={T.step.confirm}
            status={step.status}
            statusText={step.means}
            error={step.error}
            onConfirm={() => {
              void controls.declare('done');
            }}
            onDefer={() => {
              void controls.declare('later');
            }}
          />
        )}

        {finish.completion === null ? null : (
          <CompletionPanel
            completion={finish.completion}
            progress={finish.progress}
            progressFailed={finish.progressFailed}
            returnTo={`/insight/${insight.id}` as Route}
            share={share}
          />
        )}
        {finish.status === 'done' && finish.completion === null ? (
          <div className="flex flex-col items-start gap-2">
            <p className="m-0 font-semibold text-fg">{T.done.alreadyTitle}</p>
            <p className="m-0 text-fg-soft">{T.done.alreadyBody}</p>
            <LinkButton href="/world" variant="secondary">
              {messages.completion.openWorld}
            </LinkButton>
          </div>
        ) : null}
        <DisclosureLine className="pb-2" />
      </ReadingLayout>

      <WhySheet open={whyOpen} onClose={() => setWhyOpen(false)} insight={insight} />
      {canShare ? (
        <ShareSheet
          open={shareOpen}
          onClose={() => setShareOpen(false)}
          insightId={insight.id}
          insightTitle={insight.title}
          published={insight.published_at !== null}
          publishTo={publishTo}
        />
      ) : null}
      <ChatSheet
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        insightTitle={insight.title}
        // Completing the insight closes the discussion at once; the server says the same on the next load.
        chat={finish.status === 'done' ? { ...chat, closed: true } : chat}
        onAsk={controls.ask}
      />
    </>
  );
}
