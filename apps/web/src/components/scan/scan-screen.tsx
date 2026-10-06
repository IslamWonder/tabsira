'use client';

import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { type ReactNode, useEffect, useState } from 'react';
import { markTutorialClosed } from '@/account/session';
import { DisclosureLine } from '@/components/insight/disclosure-line';
import { EngineLabel } from '@/components/insight/engine-label';
import { SeenNote } from '@/components/insight/insight-frame';
import { ProgressStages, type StageId } from '@/components/insight/progress-stages';
import type { ScenePoint } from '@/components/insight/scene-photo';
import { StageLayout } from '@/components/layout/layouts';
import { SceneInsightList } from '@/components/scene/scene-insight-list';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import type { Scan } from '@/lib/scan/api';
import type { ApiStage } from '@/lib/scan/events';
import { failedRunMessage, journeyFailureMessage } from '@/lib/scan/failure';
import { centre } from '@/lib/scan/spans';
import { type ScanView, useScan } from '@/lib/scan/use-scan';
import { messages } from '@/messages';
import { ClarifyForm } from './clarify-form';
import { FocusPanel } from './focus-picker';
import { ScanStage } from './scan-stage';
import { type SoundMoment, useSceneSound } from './use-scene-sound';

const T = messages.scan;

/** The four honest stages of the API, under the names the progress component already carries. */
const STAGE_ID: Record<ApiStage, StageId> = {
  understanding: 'scene',
  searching: 'evidence',
  verifying: 'verify',
  composing: 'compose',
};

/** The insights as points of the photo; one without a box has no place in the photo, only in the list. */
function pointsOf(scan: Scan): { onPhoto: ScenePoint[]; inList: ScenePoint[] } {
  const inList = scan.insights.map((insight, index): ScenePoint => {
    const place = insight.anchor === null ? { x: 0, y: 0 } : centre(insight.anchor);
    return {
      id: insight.id,
      ...place,
      title: insight.title,
      glimpse: insight.completed ? T.completedGlimpse(insight.glimpse) : insight.glimpse,
      tone: index % 2 === 0 ? 'gold' : 'emerald',
    };
  });
  const onPhoto = inList.filter((_, index) => scan.insights[index]?.anchor !== null);
  return { onPhoto, inList };
}

function soundMoment(phase: ScanView['phase']): SoundMoment {
  if (phase === 'ready') {
    return 'ended';
  }
  return phase === 'failed' || phase === 'lost' ? 'failed' : 'running';
}

function Announce({ children }: { children: ReactNode }) {
  return (
    <div role="status" aria-live="polite" className="sr-only">
      {children}
    </div>
  );
}

/**
 * The scan (tajriba S07 and S08): the photo as the stage, and beside it, in
 * one place, whichever of these is true — the four honest stages, the
 * insights to choose from, the one clarifying question, the choice of focus,
 * an honest «no reliable link», or a failure said in words that tell the reader
 * what to do. Nothing here is invented: every state is the API's own, followed
 * on its stream and read again when a run ends.
 */
export function ScanScreen({ scanId }: { scanId: string }) {
  const router = useRouter();
  const { view, stage, sound, slow, acting, reload, focus, clarify } = useScan(scanId);
  useSceneSound(sound, soundMoment(view.phase));
  const [focusing, setFocusing] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<string | undefined>(undefined);
  const [focusError, setFocusError] = useState<string | null>(null);

  const scan = 'scan' in view ? view.scan : null;
  const running = view.phase === 'running';
  const points = scan === null ? { onPhoto: [], inList: [] } : pointsOf(scan);
  // The account's first own insight: the session learns it now, so the landing gives the capture
  // instead of the prepared example without a reload.
  const gaveInsights =
    view.phase === 'ready' && view.scan.outcome === 'insights' && view.scan.insights.length > 0;
  useEffect(() => {
    if (gaveInsights) {
      markTutorialClosed();
    }
  }, [gaveInsights]);
  const openInsight = (id: string) => router.push(`/insight/${id}` as Route);

  const stopFocusing = () => {
    setFocusing(false);
    setSelectedEntity(undefined);
    setFocusError(null);
  };
  const confirmFocus = async () => {
    const failure = await focus(selectedEntity as string);
    if (failure === null) {
      stopFocusing();
    } else {
      setFocusError(journeyFailureMessage(failure));
    }
  };

  const another = (
    <LinkButton href="/" variant="ghost">
      {T.another}
    </LinkButton>
  );
  const chooseFocus =
    scan !== null && scan.entities.length > 0 ? (
      <Button variant="secondary" onClick={() => setFocusing(true)}>
        {T.focus.open}
      </Button>
    ) : null;

  let announcement = '';
  let body: ReactNode = null;

  if (view.phase === 'loading') {
    body = <p className="m-0 text-fg-soft">{T.loading}</p>;
  } else if (view.phase === 'lost') {
    body = (
      <div className="flex flex-col items-start gap-4">
        <div role="alert">
          <Notice tone="error">{journeyFailureMessage(view.failure)}</Notice>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Button variant="secondary" onClick={reload}>
            {T.retry}
          </Button>
          {another}
        </div>
      </div>
    );
  } else if (view.phase === 'running') {
    body = (
      <>
        <ProgressStages
          current={stage === 'queued' ? 'queued' : STAGE_ID[stage]}
          slow={slow}
          onCancel={() => router.push('/')}
        />
        {view.scan.sensitive ? (
          <div role="status">
            <Notice tone="info">{T.sensitive}</Notice>
          </div>
        ) : null}
      </>
    );
  } else if (view.phase === 'failed') {
    announcement = T.failed.title;
    body = (
      <section className="flex flex-col items-start gap-4">
        <h2 className="m-0 font-semibold text-subheading text-fg">{T.failed.title}</h2>
        <p className="m-0 text-fg-soft leading-[1.9]">{failedRunMessage(view.code)}</p>
        {another}
      </section>
    );
  } else if (focusing) {
    body = (
      <FocusPanel
        entities={view.scan.entities}
        selectedId={selectedEntity}
        onSelect={setSelectedEntity}
        onConfirm={confirmFocus}
        onCancel={stopFocusing}
        acting={acting}
        error={focusError}
      />
    );
  } else if (view.scan.outcome === 'needs_clarification') {
    body = (
      <>
        <ClarifyForm
          question={view.scan.clarification_question ?? ''}
          onAnswer={clarify}
          acting={acting}
        />
        <div className="flex flex-wrap gap-2.5">
          {chooseFocus}
          {another}
        </div>
      </>
    );
  } else if (view.scan.outcome === 'insights' && view.scan.insights.length > 0) {
    announcement = messages.progress.complete;
    body = (
      <>
        <SceneInsightList points={points.inList} selectedId={undefined} onSelect={openInsight} />
        {view.scan.description === null ? null : <SeenNote text={view.scan.description} />}
        <div className="flex flex-wrap gap-2.5">
          {chooseFocus}
          {another}
        </div>
      </>
    );
  } else {
    announcement = T.noEvidence.title;
    body = (
      <section className="flex flex-col items-start gap-4">
        <h2 className="m-0 font-semibold text-subheading text-fg">{T.noEvidence.title}</h2>
        <p className="m-0 text-fg-soft leading-[1.9]">{T.noEvidence.body}</p>
        <div className="flex flex-wrap gap-2.5">
          {chooseFocus}
          {another}
        </div>
      </section>
    );
  }

  return (
    <StageLayout
      stageFirstOnPhone
      framed
      stageLabel={T.photoAlt}
      stageClassName="h-[50svh] min-h-[300px]"
      panel={
        <div className="px-4 pb-8 tablet:p-0">
          {/*
           * On a phone the panel is a card rising from the photo's faded foot, so the photo,
           * the stage being run and the way out share the first screen; from tablet up the
           * card dissolves (display: contents) into the panel beside the photo.
           */}
          <div className="glass relative z-10 -mt-12 flex flex-col gap-5 rounded-[var(--radius-panel)] p-5 shadow-[var(--panel-shadow)] tablet:mt-0 tablet:gap-6 tablet:rounded-none tablet:border-0 tablet:bg-transparent tablet:p-0 tablet:shadow-none tablet:backdrop-filter-none">
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
              <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
                {T.metaTitle}
              </h1>
              {scan === null ? null : (
                <EngineLabel engine={scan.engine} label={scan.engine_label} />
              )}
            </div>
            <Announce>{announcement}</Announce>
            {body}
            <DisclosureLine />
          </div>
        </div>
      }
      stage={
        <>
          <StageFoot />
          <ScanStage
            scan={scan}
            running={running}
            sound={sound !== null}
            focusing={focusing && scan !== null}
            selectedEntity={selectedEntity}
            onSelectEntity={setSelectedEntity}
            points={points.onPhoto}
            onSelectPoint={openInsight}
            backHref="/"
          />
        </>
      }
    />
  );
}

/** On a phone the photo melts into the page where the scan's card rises from it. */
function StageFoot() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-28 bg-[linear-gradient(to_top,var(--stage-fade)_10%,transparent)] tablet:hidden"
    />
  );
}
