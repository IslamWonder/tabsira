import type { Metadata } from 'next';
import { ResetPasswordScreen } from '@/components/account/reset-password-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.auth.reset.metaTitle,
  description: messages.auth.reset.metaDescription,
  alternates: { canonical: '/reset-password' },
  robots: { index: false, follow: false },
};

/** The token arrives after `#token=`: the server never sees it, the page reads it. */
export default function ResetPasswordPage() {
  return <ResetPasswordScreen />;
}
