import type { Metadata } from 'next';
import { ReloadButton } from '@/components/app/reload-button';
import { StatusScreen } from '@/components/app/status-screen';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.pages.offline.title,
  robots: { index: false, follow: false },
};

/** Served by the service worker when a page cannot be reached; it is static so it can be cached. */
export default function OfflinePage() {
  return (
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-6">
      <StatusScreen
        emblem="logo"
        title={messages.pages.offline.title}
        description={messages.pages.offline.description}
      >
        <ReloadButton>{messages.pages.offline.retry}</ReloadButton>
      </StatusScreen>
    </div>
  );
}
