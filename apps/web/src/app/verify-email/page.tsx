import type { Metadata } from 'next';
import { VerifyEmailScreen } from '@/components/account/verify-email-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({
  path: '/verify-email',
  title: messages.auth.verify.metaTitle,
  description: messages.auth.verify.metaDescription,
});

/** The token arrives after `#token=`: the server never sees it, the page reads it. */
export default function VerifyEmailPage() {
  return <VerifyEmailScreen />;
}
