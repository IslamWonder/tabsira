import type { Metadata } from 'next';
import { placeOnServer } from '@/atlas/server';
import { PlaceScreen } from '@/components/atlas/place-screen';
import { pageMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const dynamic = 'force-dynamic';

type Params = { params: Promise<{ id: string }> };

const GEONAME_ID = /^[1-9][0-9]{0,9}$/;

function path(id: string): string {
  return `/atlas/places/${id}`;
}

/** A place page is indexable while the place has a published entry; otherwise `noindex`. */
export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const result = GEONAME_ID.test(id) ? await placeOnServer(Number(id)) : null;
  if (result === null || !result.ok) {
    return pageMetadata({
      path: path(id),
      title: messages.atlas.title,
      description: messages.atlas.lead,
      noindex: true,
    });
  }
  const label = result.data.place.label;
  return pageMetadata({
    path: path(id),
    title: messages.atlas.place.title(label),
    description: messages.atlas.placeDescription(label),
  });
}

export default async function AtlasPlacePage({ params }: Readonly<Params>) {
  const { id } = await params;
  return <PlaceScreen geonameId={GEONAME_ID.test(id) ? Number(id) : 0} />;
}
