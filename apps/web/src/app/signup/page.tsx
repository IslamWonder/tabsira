import type { Metadata } from 'next';
import { safeNextPath } from '@/account/links';
import { SignUpScreen } from '@/components/account/sign-up-screen';
import { turnstileSiteKey } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({
  path: '/signup',
  title: messages.auth.signUp.metaTitle,
  description: messages.auth.signUp.metaDescription,
});

export default async function SignUpPage({ searchParams }: PageProps<'/signup'>) {
  return (
    <SignUpScreen
      next={safeNextPath((await searchParams).next)}
      turnstileSiteKey={turnstileSiteKey()}
    />
  );
}
