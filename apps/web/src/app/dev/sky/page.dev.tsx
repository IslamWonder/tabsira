import type { Metadata } from 'next';
import { messages } from '@/messages';
import { SkyPreview } from './sky-preview';

/*
 * Development only, like /dev/world: the `dev.tsx` page extension exists under
 * `next dev` alone, so a production build has no /dev/sky route. The sky at
 * the real page's size, to compare with the owners' reference picture.
 */

export const metadata: Metadata = {
  title: messages.devSky.title,
  robots: { index: false, follow: false },
};

export default async function DevSkyPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string }>;
}) {
  const { state } = await searchParams;
  return <SkyPreview state={state} />;
}
