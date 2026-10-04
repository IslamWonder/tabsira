import type { Metadata } from 'next';
import { VerifyEmailScreen } from '@/components/account/verify-email-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.auth.verify.metaTitle,
  description: messages.auth.verify.metaDescription,
  alternates: { canonical: '/verify-email' },
  robots: { index: false, follow: false },
};

/** The token arrives after `#token=`: the server never sees it, the page reads it. */
export default function VerifyEmailPage() {
  return <VerifyEmailScreen />;
}
