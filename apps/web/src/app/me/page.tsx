import type { Metadata } from 'next';
import { MeScreen } from '@/components/me/me-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({ path: '/me', title: messages.nav.me });

/** Private to its owner: never indexed, and every part of it comes from the session. */
export default function MePage() {
  return <MeScreen />;
}
