import type { Metadata } from 'next';
import { ar } from '@/messages/ar';
import { Gallery } from './gallery';

/*
 * Development only. next.config.ts lists the `dev.tsx` page extension under
 * `next dev` alone, so a production build has no /dev/ui route: it answers 404.
 */

export const metadata: Metadata = {
  title: ar.dev.title,
  robots: { index: false, follow: false },
};

export default function DevUiPage() {
  return <Gallery />;
}
