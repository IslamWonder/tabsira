import type { Metadata } from 'next';
import { ResetPasswordScreen } from '@/components/account/reset-password-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({
  path: '/reset-password',
  title: messages.auth.reset.metaTitle,
  description: messages.auth.reset.metaDescription,
});

/** The token arrives after `#token=`: the server never sees it, the page reads it. */
export default function ResetPasswordPage() {
  return <ResetPasswordScreen />;
}
