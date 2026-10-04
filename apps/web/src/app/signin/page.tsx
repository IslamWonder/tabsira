import type { Metadata } from 'next';
import { safeNextPath } from '@/account/links';
import { type GoogleErrorCode, SignInScreen } from '@/components/account/sign-in-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const metadata: Metadata = unlistedMetadata({
  path: '/signin',
  title: messages.auth.signIn.metaTitle,
  description: messages.auth.signIn.metaDescription,
});

function googleError(value: string | string[] | undefined): GoogleErrorCode | null {
  return typeof value === 'string' && Object.hasOwn(messages.auth.google.errors, value)
    ? (value as GoogleErrorCode)
    : null;
}

/** `?next=` is where to land afterwards; `?error=` is a failed Google sign-in (docs/AUTH.md). */
export default async function SignInPage({ searchParams }: PageProps<'/signin'>) {
  const query = await searchParams;
  return <SignInScreen next={safeNextPath(query.next)} googleError={googleError(query.error)} />;
}
