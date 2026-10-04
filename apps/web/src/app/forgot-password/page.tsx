import type { Metadata } from 'next';
import { ForgotPasswordScreen } from '@/components/account/forgot-password-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({
  path: '/forgot-password',
  title: messages.auth.forgot.metaTitle,
  description: messages.auth.forgot.metaDescription,
});

export default function ForgotPasswordPage() {
  return <ForgotPasswordScreen />;
}
