import type { Metadata } from 'next';
import { ProgressScreen } from '@/components/progress/progress-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.practiceView.title,
  alternates: { canonical: '/sky' },
  robots: { index: false, follow: false },
};

/**
 * The sky of meanings: the owner's practice, named after the night sky that heads it.
 * Private to its owner: never indexed, no analytics (`/sky` is listed with `/me`).
 */
export default function PracticePage() {
  return <ProgressScreen />;
}
