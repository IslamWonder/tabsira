import type { Metadata } from 'next';
import { MeScreen } from '@/components/me/me-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.nav.me,
  alternates: { canonical: '/me' },
  robots: { index: false, follow: false },
};

/** Private to its owner: never indexed, and every part of it comes from the session. */
export default function MePage() {
  return <MeScreen />;
}
