import type { Metadata } from 'next';
import { safeNextPath } from '@/account/links';
import { SignUpScreen } from '@/components/account/sign-up-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.auth.signUp.metaTitle,
  description: messages.auth.signUp.metaDescription,
  alternates: { canonical: '/signup' },
  robots: { index: false, follow: false },
};

export default async function SignUpPage({ searchParams }: PageProps<'/signup'>) {
  return <SignUpScreen next={safeNextPath((await searchParams).next)} />;
}
