import type { Metadata } from 'next';
import { LandingPage } from '@/components/landing/landing-page';
import { JsonLd } from '@/components/legal/json-ld';
import { landingFeatures } from '@/config/server-env';
import { organizationJsonLd, pageMetadata, webSiteJsonLd } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = pageMetadata({
  path: '/',
  title: messages.meta.title,
  absoluteTitle: true,
  description: messages.meta.description,
  share: messages.seo.homeShare,
});

/**
 * The landing page: what TABSIRA does, the prepared example and the camera, one tap each,
 * before any account or permission (tajriba A01). Its features follow the server's flags.
 */
export default function HomePage() {
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={webSiteJsonLd()} />
      <LandingPage features={landingFeatures()} />
    </>
  );
}
