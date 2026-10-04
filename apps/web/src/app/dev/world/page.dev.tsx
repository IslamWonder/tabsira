import type { Metadata } from 'next';
import { messages } from '@/messages';
import { WorldGallery } from './gallery';

/*
 * Development only, like /dev/ui: the `dev.tsx` page extension exists under
 * `next dev` alone, so a production build has no /dev/world route.
 */

export const metadata: Metadata = {
  title: messages.devWorld.title,
  robots: { index: false, follow: false },
};

export default function DevWorldPage() {
  return <WorldGallery />;
}
