'use client';

import { StatusScreen } from '@/components/app/status-screen';
import { SparkIcon } from '@/components/icons';
import { Button, LinkButton } from '@/components/ui/button';
import { ar } from '@/messages/ar';

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
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-nav">
      <StatusScreen
        icon={<SparkIcon width="28" height="28" />}
        title={ar.pages.error.title}
        description={ar.pages.error.description}
      >
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button onClick={retry}>{ar.pages.error.retry}</Button>
          <LinkButton href="/" variant="ghost">
            {ar.pages.error.home}
          </LinkButton>
        </div>
      </StatusScreen>
    </div>
  );
}
