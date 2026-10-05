'use client';

import { type ReactNode, useId, useState } from 'react';
import { LegalConsent } from '@/components/account/legal-consent';
import { SaveInvitation } from '@/components/account/save-invitation';
import { AppNav } from '@/components/app/app-nav';
import { Brand } from '@/components/app/brand';
import { TopBar } from '@/components/app/top-bar';
import { Logo, LogoMark } from '@/components/brand/logo';
import { ExternalIcon, ShareIcon } from '@/components/icons';
import { DisclosureLine } from '@/components/insight/disclosure-line';
import { DoneButton, type DoneStatus } from '@/components/insight/done-button';
import { EvidenceCard } from '@/components/insight/evidence-card';
import type { HadithRole, HadithSpan } from '@/components/insight/hadith-segments';
import {
  ExplanationBlock,
  InsightActions,
  InsightHeader,
  InsightPhoto,
  InsightTools,
  SeenNote,
} from '@/components/insight/insight-frame';
import { PhotoPlaceholder } from '@/components/insight/photo-placeholder';
import { ProgressStages, STAGES, type StageId } from '@/components/insight/progress-stages';
import { ScenePhoto, type ScenePoint } from '@/components/insight/scene-photo';
import { StepCard, type StepStatus } from '@/components/insight/step-card';
import {
  FeedLayout,
  MapLayout,
  PageContainer,
  ReadingLayout,
  SettingsLayout,
  StageLayout,
} from '@/components/layout/layouts';
import { CaptureCard } from '@/components/scene/capture-card';
import { SceneInsightList } from '@/components/scene/scene-insight-list';
import { SceneIntro } from '@/components/scene/scene-intro';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { ChoiceGroup } from '@/components/ui/choice-group';
import { GlassPanel } from '@/components/ui/glass-panel';
import { MotionSwitch } from '@/components/ui/motion-switch';
import { Notice } from '@/components/ui/notice';
import { Sheet } from '@/components/ui/sheet';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';
import { ThemeSwitcher } from '@/components/ui/theme-switcher';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { messages } from '@/messages';
import scenePlaceholder from './scene-placeholder.svg';
import { type Viewport, ViewportPreview } from './viewport-preview';

type Theme = 'light' | 'dark';

const S = messages.dev.samples;
const P = messages.dev.placeholders;
const THEMES: readonly Theme[] = ['light', 'dark'];
/** The frames are pictures: their controls answer nothing. */
const ignore = () => undefined;
const VIEWPORTS: readonly Viewport[] = ['phone', 'tablet', 'desktop'];
const SCREEN_HEIGHT: Record<Viewport, number> = { phone: 760, tablet: 900, desktop: 900 };

// Placeholders only: no verse or hadith is ever typed into the code. The spans
// are measured from the placeholder pieces, so the card proves on screen that
// the segments add back up to the text it was given.
const HADITH_PARTS: ReadonlyArray<readonly [HadithRole, string]> = [
  ['chain', P.hadithChain],
  ['body', P.hadithBody],
  ['words', P.hadithWords],
  ['tail', P.hadithTail],
];
export const HADITH_TEXT = HADITH_PARTS.map(([, part]) => part).join('');
export const HADITH_SPANS: readonly HadithSpan[] = HADITH_PARTS.reduce<HadithSpan[]>(
  (spans, [role, part]) => {
    const start = spans.at(-1)?.end ?? 0;
    spans.push({ start, end: start + part.length, role });
    return spans;
  },
  []
);

const POINTS: readonly ScenePoint[] = [
  { id: 'first', x: 0.3, y: 0.56, tone: 'gold', ...messages.dev.points[0] },
  { id: 'second', x: 0.66, y: 0.74, tone: 'emerald', ...messages.dev.points[1] },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h3 id={id} className="m-0 border-line border-b pb-2 font-semibold text-fg-soft text-lg">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Placeholder({ label, className = '' }: { label: string; className?: string }) {
  return (
    <div
      className={`flex min-h-40 items-center justify-center rounded-[var(--radius-card)] border-[1.5px] border-[var(--dropzone-border)] border-dashed text-fg-muted ${className}`}
    >
      {label}
    </div>
  );
}

function QuranSample() {
  return (
    <EvidenceCard
      variant="quran"
      headingLevel={3}
      text={P.quranText}
      reference={P.quranReference}
    />
  );
}

function SunnahSample() {
  return (
    <EvidenceCard
      variant="sunnah"
      headingLevel={3}
      text={HADITH_TEXT}
      spans={HADITH_SPANS}
      reference={P.hadithReference}
    />
  );
}

/** The scene page frame of the desktop reference, and the phone mockup below 768 px. */
function SceneFrame() {
  const [selected, setSelected] = useState<string | undefined>(undefined);
  return (
    <>
      <TopBar />
      <StageLayout
        stageFirstOnPhone
        stageLabel={messages.pages.home.stageLabel}
        stageClassName="h-[min(62svh,600px)] min-h-[340px]"
        panel={
          <div className="relative z-10 -mt-14 flex flex-col gap-6 px-4 pb-6 tablet:mt-0 tablet:gap-7 tablet:px-0 tablet:pt-2">
            <div className="sr-only tablet:not-sr-only">
              <SceneIntro chip={<Chip>{messages.scene.prepared}</Chip>} />
            </div>
            <div className="hidden tablet:block">
              <SceneInsightList points={POINTS} selectedId={selected} onSelect={setSelected} />
            </div>
            <CaptureCard onCamera={ignore} onFile={ignore} />
          </div>
        }
        stage={
          <ScenePhoto
            src={scenePlaceholder}
            alt={S.scenePlaceholderAlt}
            width={1200}
            height={1600}
            points={POINTS}
            selectedId={selected}
            onSelect={setSelected}
            listInPanel
            unoptimized
            className="h-full"
          >
            {/* The phone mockup's overlays: the name and the state on top, the hint above the invitation. */}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 pt-4 tablet:hidden">
              <LogoMark title={messages.brand.name} className="h-12" />
              <Chip tone="glass">{messages.scene.prepared}</Chip>
            </div>
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-[linear-gradient(to_top,var(--stage-fade)_15%,transparent)] tablet:hidden"
            />
            <p className="absolute inset-x-0 bottom-[4.75rem] m-0 px-4 text-center font-semibold text-fg text-lg tablet:hidden">
              {messages.scene.hint}
            </p>
          </ScenePhoto>
        }
      />
      <AppNav />
    </>
  );
}

/** The analysis while it runs: the photo not shown yet, the circle turning, the honest stages in the card. */
function ScanFrame() {
  return (
    <>
      <TopBar />
      <StageLayout
        stageFirstOnPhone
        stageLabel={messages.scan.photoAlt}
        stageClassName="h-[50svh] min-h-[300px]"
        panel={
          <div className="px-4 pb-8 tablet:p-0">
            <div className="glass relative z-10 -mt-12 flex flex-col gap-5 rounded-[var(--radius-panel)] p-5 shadow-[var(--panel-shadow)] tablet:mt-0 tablet:gap-6 tablet:rounded-none tablet:border-0 tablet:bg-transparent tablet:p-0 tablet:shadow-none tablet:backdrop-filter-none">
              <h1 className="m-0 font-bold font-display text-title text-gilded tablet:text-title-lg">
                {messages.scan.metaTitle}
              </h1>
              <ProgressStages current="evidence" onCancel={ignore} />
              <DisclosureLine />
            </div>
          </div>
        }
        stage={<PhotoPlaceholder note={messages.scan.photoWaiting} busy fill />}
      />
      <AppNav />
    </>
  );
}

/** The insight page frame of the desktop reference, and the phone mockup below 1200 px. */
function InsightFrame() {
  const [status, setStatus] = useState<DoneStatus>('idle');
  const [whyOpen, setWhyOpen] = useState(false);
  const [step, setStep] = useState<StepStatus>('idle');
  return (
    <>
      <TopBar />
      <ReadingLayout
        media={
          <InsightPhoto
            src={scenePlaceholder}
            alt={S.scenePlaceholderAlt}
            width={1200}
            height={1600}
            focus={{ x: 0.3, y: 0.56, title: messages.dev.points[0].title }}
            backHref="/"
            unoptimized
          />
        }
        footer={
          <InsightActions
            status={status}
            onDone={() => setStatus('done')}
            onShare={() => setStatus('idle')}
          />
        }
      >
        <InsightHeader
          backHref="/"
          chips={
            <>
              <Chip tone="primary">{S.chipRelation}</Chip>
              <Chip>{messages.scene.prepared}</Chip>
            </>
          }
          title={messages.dev.points[0].title}
          glimpse={messages.dev.points[0].glimpse}
        />
        <SeenNote text={S.glassBody} />
        <QuranSample />
        <SunnahSample />
        <ExplanationBlock text={P.explanation} />
        <InsightTools onWhy={() => setWhyOpen(true)} onDiscuss={() => setWhyOpen(false)} />
        <p hidden={!whyOpen} className="m-0 text-fg-soft">
          {S.sheetBody}
        </p>
        <StepCard
          body={S.stepBody}
          confirmLabel={S.stepConfirm}
          status={step}
          onConfirm={() => setStep('saved')}
          onDefer={() => setStep('deferred')}
        />
        <DisclosureLine />
      </ReadingLayout>
    </>
  );
}

function MapFrame() {
  return (
    <>
      <TopBar />
      <MapLayout
        mapLabel={messages.pages.world.mapLabel}
        panel={<Placeholder label={P.mapPanel} className="m-4" />}
        map={<Placeholder label={P.map} className="h-full rounded-none" />}
      />
    </>
  );
}

function FeedFrame() {
  return (
    <>
      <TopBar />
      <FeedLayout
        aside={<Placeholder label={P.feedAside} />}
        feed={<Placeholder label={P.feed} className="min-h-[36rem]" />}
      />
    </>
  );
}

function SettingsFrame() {
  return (
    <>
      <TopBar />
      <SettingsLayout nav={<Placeholder label={P.settingsNav} />}>
        <Placeholder label={P.settingsBody} />
        <Placeholder label={P.settingsBody} />
      </SettingsLayout>
    </>
  );
}

function Showcase({ theme }: { theme: Theme }) {
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [stage, setStage] = useState<StageId | 'done'>('scene');
  const [slow, setSlow] = useState(false);
  const [step, setStep] = useState<StepStatus>('idle');
  const [done, setDone] = useState<DoneStatus>('idle');
  const [received, setReceived] = useState<string>(S.nothingYet);
  const [switchOn, setSwitchOn] = useState(true);
  const [choice, setChoice] = useState('0');
  const [accepted, setAccepted] = useState(false);

  const nextStage = () => {
    setStage((current) => {
      if (current === 'done') {
        return 'scene';
      }
      return STAGES[STAGES.indexOf(current) + 1] ?? 'done';
    });
  };
  const selectedPoint = POINTS.find((point) => point.id === selected);
  const confirmStep = () => setStep('saved');
  const deferStep = () => setStep('deferred');

  return (
    <div className="flex flex-col gap-10">
      <Section title={messages.dev.sections.brand}>
        <div className="flex flex-wrap items-center gap-6">
          <Brand />
          <Logo title={messages.brand.name} className="h-28" />
          <ThemeToggle />
        </div>
      </Section>

      <Section title={messages.dev.sections.fields}>
        <TextField label={S.fieldLabel} hint={S.fieldHint} />
        <TextField label={S.fieldLabel} error={S.fieldError} type="password" revealable />
        <Notice tone="success">{S.notice}</Notice>
        <Notice tone="error">{S.notice}</Notice>
        <Notice tone="info">{S.notice}</Notice>
        <SwitchRow
          label={S.switchLabel}
          hint={S.switchHint}
          checked={switchOn}
          onChange={setSwitchOn}
        />
        <ChoiceGroup
          legend={S.choiceLegend}
          options={S.choices.map((label, index) => ({ value: String(index), label }))}
          value={choice}
          onChange={setChoice}
        />
        <LegalConsent checked={accepted} onChange={setAccepted} />
      </Section>

      <Section title={messages.dev.sections.invitation}>
        <SaveInvitation returnTo="/" />
      </Section>

      <Section title={messages.dev.sections.buttons}>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg">{S.primary}</Button>
          <Button variant="secondary">{S.secondary}</Button>
          <Button variant="ghost">{S.ghost}</Button>
          <Button variant="icon" label={S.share}>
            <ShareIcon />
          </Button>
          <Button disabled>{S.disabled}</Button>
          <LinkButton href="/" variant="secondary">
            {messages.pages.notFound.action}
          </LinkButton>
        </div>
      </Section>

      <Section title={messages.dev.sections.done}>
        <DoneButton status={done} onDone={() => setDone('done')} />
        <div>
          <Button variant="ghost" onClick={() => setDone('idle')}>
            {S.reset}
          </Button>
        </div>
      </Section>

      <Section title={messages.dev.sections.chips}>
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone="primary">{S.chipRelation}</Chip>
          <Chip>{messages.comingSoon.badge}</Chip>
          <Chip tone="quran">{messages.evidence.quran}</Chip>
          <Chip tone="sunnah">{messages.evidence.sunnah}</Chip>
          <Chip tone="glass" icon={<ExternalIcon />}>
            {messages.scene.prepared}
          </Chip>
        </div>
      </Section>

      <Section title={messages.dev.sections.glass}>
        <GlassPanel as="section" aria-label={S.glassTitle}>
          <p className="m-0 font-semibold text-fg">{S.glassTitle}</p>
          <p className="m-0 text-fg-soft text-sm">{S.glassBody}</p>
        </GlassPanel>
      </Section>

      <Section title={messages.dev.sections.theme}>
        <ThemeSwitcher />
      </Section>

      <Section title={messages.dev.sections.motion}>
        <MotionSwitch />
      </Section>

      <Section title={messages.dev.sections.sheet}>
        <div>
          <Button variant="secondary" onClick={() => setSheetOpen(true)}>
            {S.openSheet}
          </Button>
        </div>
        <Sheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={S.sheetTitle}
          theme={theme}
        >
          <p className="m-0 text-fg-soft">{S.sheetBody}</p>
        </Sheet>
      </Section>

      <Section title={messages.dev.sections.scene}>
        <ScenePhoto
          src={scenePlaceholder}
          alt={S.scenePlaceholderAlt}
          width={1200}
          height={1600}
          points={POINTS}
          selectedId={selected}
          onSelect={setSelected}
          unoptimized
          className="h-[520px] rounded-[28px]"
        >
          <div className="absolute inset-x-0 top-0 flex justify-start p-4">
            <Chip tone="glass">{messages.scene.prepared}</Chip>
          </div>
        </ScenePhoto>
        <p role="status" className="m-0 text-fg-soft text-sm">
          {S.selected} {selectedPoint === undefined ? S.none : selectedPoint.title}
        </p>
      </Section>

      <Section title={messages.dev.sections.list}>
        <SceneInsightList points={POINTS} selectedId={selected} onSelect={setSelected} />
      </Section>

      <Section title={messages.dev.sections.starter}>
        <CaptureCard
          onCamera={() => setReceived(messages.nav.captureScene)}
          onFile={(file) => setReceived(`${S.picked} ${file.name}`)}
        />
        <p role="status" className="m-0 text-fg-soft text-sm" dir="auto">
          {received}
        </p>
      </Section>

      <Section title={messages.dev.sections.evidence}>
        <QuranSample />
        <SunnahSample />
      </Section>

      <Section title={messages.dev.sections.progress}>
        <ProgressStages current={stage} slow={slow} onCancel={() => setStage('scene')} />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={nextStage}>
            {S.next}
          </Button>
          <Button variant="ghost" aria-pressed={slow} onClick={() => setSlow((value) => !value)}>
            {S.slow}
          </Button>
        </div>
      </Section>

      <Section title={messages.dev.sections.step}>
        <StepCard
          body={S.stepBody}
          confirmLabel={S.stepConfirm}
          status={step}
          onConfirm={confirmStep}
          onDefer={deferStep}
        />
        <StepCard
          body={S.stepBody}
          confirmLabel={S.stepConfirm}
          status="saving"
          onConfirm={confirmStep}
          onDefer={deferStep}
        />
        <div>
          <Button variant="ghost" onClick={() => setStep('idle')}>
            {S.reset}
          </Button>
        </div>
      </Section>

      <Section title={messages.dev.sections.disclosure}>
        <DisclosureLine />
      </Section>
    </div>
  );
}

function FrameSection({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <PageContainer>
      <section aria-labelledby={id} className="flex flex-col gap-5">
        <h2 id={id} className="m-0 font-bold font-display text-2xl text-fg">
          {title}
        </h2>
        {children}
      </section>
    </PageContainer>
  );
}

/**
 * Every component in both themes, and the real shell at the three breakpoints
 * (phone, tablet, desktop) in both themes, with the scene and insight frames
 * of the reference designs and the other layout primitives.
 */
export function Gallery() {
  return (
    <div className="flex flex-col gap-12 pt-[max(28px,env(safe-area-inset-top))] pb-6 tablet:pb-12">
      <PageContainer>
        <header className="flex flex-col gap-1">
          <h1 className="m-0 font-bold font-display text-3xl text-fg">{messages.dev.title}</h1>
          <p className="m-0 text-fg-soft">{messages.dev.description}</p>
        </header>
      </PageContainer>

      <FrameSection title={messages.dev.frames.shell}>
        {THEMES.map((theme) => (
          <div key={theme} className="flex flex-col gap-3">
            <h3 className="m-0 font-semibold text-fg-soft text-lg">{messages.dev.themes[theme]}</h3>
            <div className="grid gap-5 desktop:grid-cols-[1fr_1.6fr_2.4fr]">
              {VIEWPORTS.map((viewport) => (
                <ViewportPreview
                  key={viewport}
                  viewport={viewport}
                  theme={theme}
                  height={SCREEN_HEIGHT[viewport]}
                  label={messages.dev.viewports[viewport]}
                >
                  <SceneFrame />
                </ViewportPreview>
              ))}
            </div>
          </div>
        ))}
      </FrameSection>

      <FrameSection title={messages.dev.frames.scan}>
        <div className="grid gap-5 desktop:grid-cols-[1fr_3fr]">
          <ViewportPreview
            viewport="phone"
            theme="dark"
            height={SCREEN_HEIGHT.phone}
            label={messages.dev.viewports.phone}
          >
            <ScanFrame />
          </ViewportPreview>
          <ViewportPreview
            viewport="desktop"
            theme="light"
            height={SCREEN_HEIGHT.desktop}
            label={messages.dev.viewports.desktop}
          >
            <ScanFrame />
          </ViewportPreview>
        </div>
      </FrameSection>

      <FrameSection title={messages.dev.frames.insight}>
        <div className="grid gap-5 desktop:grid-cols-[1fr_3fr]">
          <ViewportPreview
            viewport="phone"
            theme="dark"
            height={1640}
            label={messages.dev.viewports.phone}
          >
            <InsightFrame />
          </ViewportPreview>
          <ViewportPreview
            viewport="desktop"
            theme="light"
            height={1500}
            label={messages.dev.viewports.desktop}
          >
            <InsightFrame />
          </ViewportPreview>
        </div>
      </FrameSection>

      <FrameSection title={messages.dev.frames.layouts}>
        <div className="grid gap-5 desktop:grid-cols-3">
          <ViewportPreview
            viewport="desktop"
            theme="light"
            height={900}
            label={messages.dev.layouts.map}
          >
            <MapFrame />
          </ViewportPreview>
          <ViewportPreview
            viewport="desktop"
            theme="dark"
            height={900}
            label={messages.dev.layouts.feed}
          >
            <FeedFrame />
          </ViewportPreview>
          <ViewportPreview
            viewport="desktop"
            theme="light"
            height={900}
            label={messages.dev.layouts.settings}
          >
            <SettingsFrame />
          </ViewportPreview>
        </div>
      </FrameSection>

      <FrameSection title={messages.dev.frames.components}>
        <div className="grid gap-6 desktop:grid-cols-2">
          {THEMES.map((theme) => (
            <section
              key={theme}
              data-theme={theme}
              aria-label={messages.dev.themes[theme]}
              className="stage-aurora flex flex-col gap-6 rounded-[28px] border border-line p-4 tablet:p-6"
            >
              <h3 className="m-0 font-bold font-display text-2xl text-fg">
                {messages.dev.themes[theme]}
              </h3>
              <Showcase theme={theme} />
            </section>
          ))}
        </div>
      </FrameSection>
    </div>
  );
}
