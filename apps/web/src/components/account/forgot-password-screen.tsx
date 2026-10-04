'use client';

import Link from 'next/link';
import { api } from '@/lib/api/client';
import { attempt } from '@/lib/api/result';
import { messages } from '@/messages';
import { EmailRequestForm } from './email-request-form';
import { Gate } from './gate';

const T = messages.auth.forgot;

const requestReset = (email: string) =>
  attempt(api.POST('/auth/forgot-password', { body: { email } }));

/** Ask for a password reset link; the answer never says whether the address has an account. */
export function ForgotPasswordScreen() {
  return (
    <Gate
      title={T.title}
      lead={T.lead}
      footer={
        <Link href="/signin" className="inline-flex min-h-12 items-center text-link">
          {T.backToSignIn}
        </Link>
      }
    >
      <EmailRequestForm
        request={requestReset}
        submitLabel={T.submit}
        busyLabel={T.submitting}
        acceptedMessage={T.sent}
      />
    </Gate>
  );
}
