import type { Metadata } from 'next';
import { ProgressScreen } from '@/components/progress/progress-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.practiceView.title,
  alternates: { canonical: '/me/practice' },
  robots: { index: false, follow: false },
};

/** Private to its owner, under the profile tab so that tab stays the active one. */
export default function PracticePage() {
  return <ProgressScreen />;
}
