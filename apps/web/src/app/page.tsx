import type { Metadata } from 'next';
import { CommunitySummary } from '@/components/landing/community-summary';
import { LandingPage } from '@/components/landing/landing-page';
import { JsonLd } from '@/components/legal/json-ld';
import { landingFeatures } from '@/config/server-env';
import { communitySummaryOnServer, shownSummary } from '@/lib/community-summary';
import { organizationJsonLd, pageMetadata, webSiteJsonLd } from '@/lib/seo';
import { messages } from '@/messages';

// The community box's counts are read again at most every ten minutes (the API's own cache).
export const revalidate = 600;

export const metadata: Metadata = pageMetadata({
  path: '/',
  title: messages.meta.title,
  absoluteTitle: true,
  description: messages.meta.description,
  share: messages.seo.homeShare,
});

/**
 * The landing page: what TABSIRA does, the prepared example and the camera, one tap each,
 * before any account or permission (tajriba A01). Its features follow the server's flags. The
 * community box is left out when the API fails or the community is still small.
 */
export default async function HomePage() {
  const summary = shownSummary(await communitySummaryOnServer());
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={webSiteJsonLd()} />
      <LandingPage
        features={landingFeatures()}
        community={summary === null ? null : <CommunitySummary summary={summary} />}
      />
    </>
  );
}
