import { LegalPage } from '@/components/legal/legal-page';
import { legalMetadata } from '@/lib/legal-seo';
import { legalMessages } from '@/messages/legal';

const { sources } = legalMessages();
const SEO = { path: '/sources', title: sources.title, description: sources.description } as const;

export const metadata = legalMetadata(SEO);

export default function SourcesPage() {
  return <LegalPage document={sources} seo={SEO} />;
}
