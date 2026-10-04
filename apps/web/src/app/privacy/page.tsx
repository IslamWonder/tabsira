import { LegalPage } from '@/components/legal/legal-page';
import { legalMetadata } from '@/lib/legal-seo';
import { legalMessages } from '@/messages/legal';

const { privacy } = legalMessages();
const SEO = { path: '/privacy', title: privacy.title, description: privacy.description } as const;

export const metadata = legalMetadata(SEO);

export default function PrivacyPage() {
  return <LegalPage document={privacy} seo={SEO} />;
}
