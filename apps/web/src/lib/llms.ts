import { absoluteUrl, type INDEXED_ROUTES } from '@/lib/seo';
import { messages } from '@/messages';
import { type LegalDocument, legalMessages } from '@/messages/legal';

/*
 * llms.txt and llms-full.txt (docs/SEO.md §4), written from the routes and the
 * messages module. Useful to agents, not a ranking lever. They carry the
 * site's own text only: no insight, no scripture, nothing of a person.
 */

const { terms, privacy, support } = legalMessages();

interface PageEntry {
  path: (typeof INDEXED_ROUTES)[number];
  title: string;
  description: string;
}

const PAGES: readonly PageEntry[] = [
  { path: '/', title: messages.meta.siteName, description: messages.meta.description },
  { path: '/terms', title: terms.title, description: terms.description },
  { path: '/privacy', title: privacy.title, description: privacy.description },
  { path: '/support', title: support.title, description: support.description },
];

function head(): string[] {
  return [
    `# ${messages.meta.siteName}`,
    '',
    `> ${messages.meta.description}`,
    '',
    `## ${messages.seo.llms.summaryHeading}`,
    '',
    messages.brand.promise,
    '',
    `## ${messages.seo.llms.rulesHeading}`,
    '',
    ...messages.seo.llms.rules.map((rule) => `- ${rule}`),
    '',
  ];
}

function pageLines(page: PageEntry): string {
  return `- [${page.title}](${absoluteUrl(page.path)}): ${page.description}`;
}

export function llmsTxt(): string {
  return [...head(), `## ${messages.seo.llms.pagesHeading}`, '', ...PAGES.map(pageLines), ''].join(
    '\n'
  );
}

function documentLines(document: LegalDocument, path: string): string[] {
  return [
    `## ${document.title}`,
    '',
    absoluteUrl(path),
    '',
    document.intro,
    '',
    ...document.sections.flatMap((section) => [
      `### ${section.heading}`,
      '',
      ...section.blocks.flatMap((block) =>
        block.kind === 'p' ? [block.text, ''] : [...block.items.map((item) => `- ${item}`), '']
      ),
    ]),
  ];
}

export function llmsFullTxt(): string {
  return [
    ...head(),
    `## ${messages.seo.llms.pagesHeading}`,
    '',
    ...PAGES.map(pageLines),
    '',
    ...documentLines(terms, '/terms'),
    ...documentLines(privacy, '/privacy'),
  ].join('\n');
}
