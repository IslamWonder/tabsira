import Link from 'next/link';
import { SeedlingIcon } from '@/components/icons';
import { DisclosureLine } from '@/components/insight/disclosure-line';
import { ExplanationSections } from '@/components/insight/explanation-sections';
import { InsightEvidence } from '@/components/insight/insight-evidence';
import { JsonLd } from '@/components/legal/json-ld';
import { Chip } from '@/components/ui/chip';
import { publicInsightSeo } from '@/lib/public-insight';
import type { PublicInsight } from '@/lib/scan/api';
import { articleJsonLd, breadcrumbJsonLd, webPageJsonLd } from '@/lib/seo';
import { messages, siteLanguage } from '@/messages';

/*
 * A published insight as anyone reads it (master prompt v2 §18): the title and
 * glimpse, what the photo showed, the verse and the hadith exactly as the API
 * returns them from the store, the platform's explanation, the why section, the
 * small step and the disclosure. No photo, no chat, no profile, no learning
 * history: the API sends none of it, and the page prints only what it sends.
 * Structured data names only what the page prints (docs/SEO.md §3).
 */

function PublishedOn({ at }: { at: string }) {
  const date = new Date(at);
  return (
    <time dateTime={at} className="text-fg-muted text-sm">
      {messages.publicInsight.publishedOn}{' '}
      {date.toLocaleDateString(siteLanguage.intl, { dateStyle: 'long' })}
    </time>
  );
}

/** What the photo showed, kept apart from any interpretation (tajriba §3.8). */
function Seen({ text }: { text: string }) {
  return (
    <p className="m-0 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-[0.9375rem] text-fg-soft leading-[1.75]">
      <strong className="font-medium text-fg">{messages.insight.seen}</strong> {text}
    </p>
  );
}

/** The why section for everyone: the clues, the concept and the limits, as the API gives them. */
function Why({ why }: { why: PublicInsight['why'] }) {
  const T = messages.insightPage.why;
  return (
    <section
      aria-label={T.title}
      className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-4"
    >
      <h2 className="m-0 font-semibold text-[1.0625rem] text-fg">{T.title}</h2>
      <dl className="m-0 flex flex-col gap-3 text-[0.9375rem] leading-[1.8]">
        {why.visible_clues.length === 0 ? null : (
          <div>
            <dt className="font-semibold text-fg-soft">{T.clues}</dt>
            <dd className="m-0">{why.visible_clues.join(messages.publicInsight.listSeparator)}</dd>
          </div>
        )}
        <div>
          <dt className="font-semibold text-fg-soft">{T.concept}</dt>
          <dd className="m-0">{why.concept}</dd>
        </div>
        {why.limits.length === 0 ? null : (
          <div>
            <dt className="font-semibold text-fg-soft">{T.limits}</dt>
            <dd className="m-0">
              <ul className="m-0 flex list-disc flex-col gap-1 ps-5">
                {why.limits.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}

/** The small step, to read: the owner's declaration about it is theirs alone. */
function Step({ step }: { step: NonNullable<PublicInsight['small_step']> }) {
  return (
    <section
      aria-label={messages.step.title}
      className="surface-step flex flex-col gap-2 rounded-[var(--radius-panel)] p-[18px]"
    >
      <h2 className="m-0 flex flex-wrap items-center gap-2 font-semibold text-[1.0625rem] text-step-title">
        <SeedlingIcon width="20" height="20" />
        {messages.step.title}
        <Chip tone={step.kind === 'text_grounded' ? 'sunnah' : 'neutral'}>{step.label}</Chip>
      </h2>
      <p className="m-0 text-[0.96875rem] text-fg leading-[1.85]">{step.text}</p>
    </section>
  );
}

export function PublicInsightArticle({ insight }: { insight: PublicInsight }) {
  const T = messages.publicInsight;
  const seo = publicInsightSeo(insight);
  const seen = insight.explanation.find((part) => part.section === 'seen');
  return (
    <article className="mx-auto flex w-full max-w-[680px] flex-col gap-[18px] px-[18px] py-6 tablet:px-6 desktop:py-10">
      <JsonLd data={webPageJsonLd(seo, insight.published_at)} />
      <JsonLd data={breadcrumbJsonLd([{ name: T.name, path: seo.path }])} />
      <JsonLd
        data={articleJsonLd({
          path: seo.path,
          headline: insight.title,
          datePublished: insight.published_at,
          authorName: insight.author?.public_name,
        })}
      />
      <header className="flex flex-col gap-2 desktop:gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone="neutral">{T.name}</Chip>
          <Chip>{insight.relation_label}</Chip>
          {insight.label === null ? null : <Chip tone="primary">{insight.label}</Chip>}
        </div>
        <h1 className="m-0 font-bold font-display text-[2rem] text-gilded leading-[1.3] desktop:text-[2.5rem]">
          {insight.title}
        </h1>
        <p className="m-0 text-[1.0625rem] text-fg-soft leading-[1.85] desktop:text-lg">
          {insight.glimpse}
        </p>
        <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-fg-muted text-sm">
          {insight.author === null ? null : <span>{T.byAuthor(insight.author.public_name)}</span>}
          <PublishedOn at={insight.published_at} />
        </p>
      </header>
      {seen === undefined ? null : <Seen text={seen.text} />}
      <InsightEvidence insight={insight} />
      <ExplanationSections tag={insight.explanation_tag} parts={insight.explanation} />
      <Why why={insight.why} />
      {insight.small_step === null ? null : <Step step={insight.small_step} />}
      <aside className="flex flex-col items-start gap-2 rounded-[var(--radius-card)] border border-line bg-surface px-4 py-4">
        <p className="m-0 text-[0.9375rem] text-fg-soft leading-[1.75]">{T.tryItHint}</p>
        <Link href="/" className="font-semibold text-link">
          {T.tryIt}
        </Link>
      </aside>
      <DisclosureLine className="pb-2" />
    </article>
  );
}
