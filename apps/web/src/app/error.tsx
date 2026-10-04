'use client';

import { StatusScreen } from '@/components/app/status-screen';
import { Button, LinkButton } from '@/components/ui/button';
import { messages } from '@/messages';

export interface ErrorPageProps {
  error: Error & { digest?: string };
  /** Fetches and renders the segment again (Next.js 16). */
  retry: () => void;
}

/**
 * A failure is ours, never the reader's (tajriba §7). Nothing from the error is
 * shown: in production its message is generic anyway, and the digest is for
 * server logs, not for people.
 */
export default function ErrorPage({ retry }: ErrorPageProps) {
  return (
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-6">
      <StatusScreen
        emblem="logo"
        title={messages.pages.error.title}
        description={messages.pages.error.description}
      >
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button onClick={retry}>{messages.pages.error.retry}</Button>
          <LinkButton href="/" variant="ghost">
            {messages.pages.error.home}
          </LinkButton>
        </div>
      </StatusScreen>
    </div>
  );
}
