import { LegalPage } from '@/components/legal/legal-page';
import { legalMetadata } from '@/lib/legal-seo';
import { legalMessages } from '@/messages/legal';

const { terms } = legalMessages();
const SEO = { path: '/terms', title: terms.title, description: terms.description } as const;

export const metadata = legalMetadata(SEO);

export default function TermsPage() {
  return <LegalPage document={terms} seo={SEO} />;
}
