import type { Metadata } from 'next';
import { ForgotPasswordScreen } from '@/components/account/forgot-password-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.auth.forgot.metaTitle,
  description: messages.auth.forgot.metaDescription,
  alternates: { canonical: '/forgot-password' },
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordScreen />;
}
