import type { Metadata } from 'next';
import { JsonLd } from '@/components/legal/json-ld';
import { SceneExperience } from '@/components/scene/scene-experience';
import { organizationJsonLd, pageMetadata, webSiteJsonLd } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = pageMetadata({
  path: '/',
  title: messages.meta.title,
  absoluteTitle: true,
  description: messages.meta.description,
  share: messages.seo.homeShare,
});

/** The scene: the prepared rain photo first, before any account or permission (tajriba A01). */
export default function ScenePage() {
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={webSiteJsonLd()} />
      <SceneExperience />
    </>
  );
}
