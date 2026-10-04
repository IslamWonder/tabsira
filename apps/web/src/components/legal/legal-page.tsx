import Link from 'next/link';
import { SettingsLayout } from '@/components/layout/layouts';
import { Chip } from '@/components/ui/chip';
import { GlassPanel } from '@/components/ui/glass-panel';
import { type LegalPageSeo, webPageJsonLd } from '@/lib/legal-seo';
import { breadcrumbJsonLd } from '@/lib/seo';
import { type LegalDocument, legalMessages } from '@/messages/legal';
import { JsonLd } from './json-ld';
import { RichText } from './rich-text';

const COMMON = legalMessages().common;

const LINK =
  'flex min-h-12 items-center rounded-[var(--radius-card)] px-4 text-fg-soft transition-colors duration-200 hover:bg-surface hover:text-fg';

function TableOfContents({ document }: { document: LegalDocument }) {
  return (
    <nav aria-label={COMMON.toc}>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {document.sections.map((section) => (
          <li key={section.id}>
            <a href={`#${section.id}`} className={LINK}>
              {section.heading}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

interface LegalPageProps {
  document: LegalDocument;
  seo: LegalPageSeo;
}

/**
 * A legal text as a calm reading page (tajriba: one task, no distraction): one
 * glass panel with a measure of about 46 rem, which suits Arabic at this size,
 * a table of contents that is sticky on tablet and desktop and folds into a
 * disclosure on a phone, and anchors on every section.
 */
export function LegalPage({ document, seo }: LegalPageProps) {
  return (
    <SettingsLayout
      className="pt-[max(28px,env(safe-area-inset-top))] pb-nav tablet:pb-8"
      nav={<TableOfContents document={document} />}
    >
      <JsonLd data={webPageJsonLd(seo, document.version)} />
      <JsonLd data={breadcrumbJsonLd([{ name: seo.title, path: seo.path }])} />
      <GlassPanel
        as="article"
        ornate
        className="motion-safe:animate-fade-in mx-auto w-full max-w-[46rem] p-5 tablet:p-8"
      >
        <header className="flex flex-col gap-3">
          <h1 className="m-0 font-bold text-[2rem] text-gilded tablet:text-[2.5rem]">
            {document.title}
          </h1>
          <p className="m-0 flex flex-wrap items-center gap-2 text-fg-soft text-sm">
            <Chip tone="primary">
              {COMMON.version} {document.version}
            </Chip>{' '}
            {/* A real space: text extraction ignores the flex layout and would weld the date to the version. */}
            <span>
              {COMMON.updated}: <time dateTime={document.version}>{document.updated}</time>
            </span>
          </p>
          <p className="m-0 text-fg leading-[2]">
            <RichText text={document.intro} />
          </p>
        </header>

        <details className="mt-5 rounded-[var(--radius-card)] border border-line bg-surface tablet:hidden">
          <summary className="flex min-h-12 cursor-pointer items-center px-4 font-medium text-fg">
            {COMMON.tocOpen}
          </summary>
          <div className="px-2 pb-2">
            <TableOfContents document={document} />
          </div>
        </details>

        <div className="mt-6 flex flex-col gap-8">
          {document.sections.map((section) => (
            <section
              key={section.id}
              id={section.id}
              aria-labelledby={`${section.id}-title`}
              className="scroll-mt-[calc(var(--topbar-height)+1rem)] border-line border-t pt-6"
            >
              <h2
                id={`${section.id}-title`}
                className="m-0 mb-3 font-bold font-sans text-[1.375rem] text-fg"
              >
                {section.heading}
              </h2>
              <div className="flex flex-col gap-3 text-fg leading-[2]">
                {section.blocks.map((block) =>
                  block.kind === 'p' ? (
                    <p key={block.text} className="m-0">
                      <RichText text={block.text} />
                    </p>
                  ) : (
                    <ul
                      key={block.items.join('|')}
                      className="m-0 flex list-disc flex-col gap-2 ps-6"
                    >
                      {block.items.map((item) => (
                        <li key={item}>
                          <RichText text={item} />
                        </li>
                      ))}
                    </ul>
                  )
                )}
              </div>
            </section>
          ))}
        </div>

        <nav aria-label={COMMON.relatedLabel} className="mt-8 border-line border-t pt-4">
          <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-1 p-0">
            {(['terms', 'privacy', 'support'] as const)
              .filter((key) => `/${key}` !== seo.path)
              .map((key) => (
                <li key={key}>
                  <Link
                    href={`/${key}`}
                    className="inline-flex min-h-12 items-center text-link underline"
                  >
                    {COMMON.related[key]}
                  </Link>
                </li>
              ))}
          </ul>
        </nav>
      </GlassPanel>
    </SettingsLayout>
  );
}
