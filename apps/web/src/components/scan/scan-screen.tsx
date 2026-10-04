'use client';

import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { type ReactNode, useState } from 'react';
import { EdgeGlow } from '@/components/fx/edge-glow';
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
import { useScan } from '@/lib/scan/use-scan';
import { messages } from '@/messages';
import { ClarifyForm } from './clarify-form';
import { FocusPanel } from './focus-picker';
import { ScanStage } from './scan-stage';

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
  const { view, stage, slow, acting, reload, focus, clarify } = useScan(scanId);
  const [focusing, setFocusing] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<string | undefined>(undefined);
  const [focusError, setFocusError] = useState<string | null>(null);

  const scan = 'scan' in view ? view.scan : null;
  const running = view.phase === 'running';
  const points = scan === null ? { onPhoto: [], inList: [] } : pointsOf(scan);
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
        <h2 className="m-0 font-semibold text-[1.25rem] text-fg">{T.failed.title}</h2>
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
        {view.scan.awaiting_verification > 0 ? (
          <Notice tone="info">{T.noEvidence.awaiting}</Notice>
        ) : null}
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
        <h2 className="m-0 font-semibold text-[1.25rem] text-fg">{T.noEvidence.title}</h2>
        <p className="m-0 text-fg-soft leading-[1.9]">{T.noEvidence.body}</p>
        {view.scan.awaiting_verification > 0 ? (
          <Notice tone="info">{T.noEvidence.awaiting}</Notice>
        ) : null}
        <div className="flex flex-wrap gap-2.5">
          {chooseFocus}
          {another}
        </div>
      </section>
    );
  }

  return (
    <>
      <EdgeGlow active={running} />
      <StageLayout
        stageFirstOnPhone
        stageLabel={T.photoAlt}
        stageClassName="h-[52dvh] min-h-[320px]"
        panel={
          <div className="flex flex-col gap-6 px-4 pt-5 pb-[calc(var(--nav-clearance)+2rem)] tablet:p-0">
            <h1 className="m-0 font-bold font-display text-[2rem] text-gilded leading-[1.3]">
              {T.metaTitle}
            </h1>
            <Announce>{announcement}</Announce>
            {scan === null ? null : <EngineLabel engine={scan.engine} label={scan.engine_label} />}
            {body}
            <DisclosureLine />
          </div>
        }
        stage={
          <ScanStage
            scan={scan}
            running={running}
            focusing={focusing && scan !== null}
            selectedEntity={selectedEntity}
            onSelectEntity={setSelectedEntity}
            points={points.onPhoto}
            onSelectPoint={openInsight}
            backHref="/"
          />
        }
      />
    </>
  );
}
