import { SparkIcon } from '@/components/icons';
import { LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { DISPLAY_TIME_ZONE, formatDay } from '@/lib/dates';
import type { PublicInsight } from '@/lib/public-insight';
import { messages } from '@/messages';
import { EngineLabel } from './engine-label';
import { ExplanationSections } from './explanation-sections';
import { InsightEvidence } from './insight-evidence';

const T = messages.publicInsight;

/** The owner's chosen public handle and name, exactly as given; nothing else identifies them. */
function Author({ author }: { author: NonNullable<PublicInsight['author']> }) {
  return (
    <p className="m-0 flex flex-wrap items-center gap-x-2 text-[0.9375rem] text-fg-soft">
      <span className="sr-only">{T.authorLabel}:</span>
      <span className="font-medium text-fg">{author.public_name}</span>
      <span dir="ltr" className="text-fg-muted">
        @{author.handle}
      </span>
    </p>
  );
}

function SmallStep({ step }: { step: NonNullable<PublicInsight['small_step']> }) {
  return (
    <section
      aria-label={T.stepTitle}
      className="surface-sunnah flex flex-col items-start gap-2 rounded-[var(--radius-card)] px-5 py-4"
    >
      <Chip tone="primary">{step.label}</Chip>
      <p className="m-0 text-[1.0625rem] text-fg leading-[1.9]">{step.text}</p>
    </section>
  );
}

/** The way into the app, in the direction's style: one glowing action, one quiet one (Von Restorff, Hick). */
function Invitation() {
  return (
    <section
      aria-labelledby="public-insight-call"
      className="glass flex flex-col gap-3 rounded-[var(--radius-panel)] p-5"
    >
      <h2 id="public-insight-call" className="m-0 font-display font-bold text-[1.375rem] text-fg">
        {T.callTitle}
      </h2>
      <p className="m-0 text-fg-soft leading-[1.9]">{T.callBody}</p>
      <div className="flex flex-col gap-2 tablet:flex-row">
        <LinkButton href="/" variant="cta" size="lg" className="tablet:flex-1">
          {messages.nav.captureScene}
        </LinkButton>
        <LinkButton href="/signin" variant="secondary" size="lg" className="tablet:flex-1">
          {T.callSignIn}
        </LinkButton>
      </div>
    </section>
  );
}

/**
 * One published insight for any reader (task 09.2): the title and glimpse, the
 * verse and the hadith exactly as the API returns them, the platform's
 * explanation and step, and the AI disclosure. It shows only what the public
 * answer holds: no photo, place, chat or progress, and the author only when the
 * owner chose a public handle and name.
 */
export function PublicInsightPage({ insight }: { insight: PublicInsight }) {
  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-6 px-4 pt-[max(28px,env(safe-area-inset-top))] pb-8 tablet:px-6 tablet:pb-10">
      <article className="motion-safe:animate-fade-in flex flex-col gap-6">
        <EngineLabel engine={insight.engine} label={insight.label} />
        <header className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Chip>{insight.relation_label}</Chip>
          </div>
          <h1 className="m-0 font-bold font-display text-[2rem] text-gilded leading-[1.3] tablet:text-[2.5rem]">
            {insight.title}
          </h1>
          <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85] tablet:text-lg">
            {insight.glimpse}
          </p>
          {insight.author === null ? null : <Author author={insight.author} />}
          <p className="m-0 text-[0.8125rem] text-fg-muted">
            <time dateTime={insight.published_at}>
              {T.publishedOn(formatDay(insight.published_at, DISPLAY_TIME_ZONE))}
            </time>
          </p>
        </header>
        <InsightEvidence insight={insight} />
        {insight.notice !== null && insight.hadith_status !== 'awaiting_verification' ? (
          <div role="note">
            <Notice tone="info">{insight.notice}</Notice>
          </div>
        ) : null}
        <ExplanationSections tag={insight.explanation_tag} parts={insight.explanation} />
        {insight.small_step === null ? null : <SmallStep step={insight.small_step} />}
        {/* The share action and the share image of task 09.3 go here, after the content and before the invitation. */}
        <p className="m-0 flex items-center justify-center gap-1.5 text-center text-[0.8125rem] text-fg-muted leading-relaxed">
          <SparkIcon width="15" height="15" className="shrink-0" />
          {insight.disclosure}
        </p>
      </article>
      <Invitation />
    </div>
  );
}
