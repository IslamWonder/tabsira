import type { Metadata } from 'next';
import { ReloadButton } from '@/components/app/reload-button';
import { StatusScreen } from '@/components/app/status-screen';
import { OfflineIcon } from '@/components/icons';
import { ar } from '@/messages/ar';

export const metadata: Metadata = {
  title: ar.pages.offline.title,
  robots: { index: false, follow: false },
};

/** Served by the service worker when a page cannot be reached; it is static so it can be cached. */
export default function OfflinePage() {
  return (
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-nav">
      <StatusScreen
        icon={<OfflineIcon width="28" height="28" />}
        title={ar.pages.offline.title}
        description={ar.pages.offline.description}
      >
        <ReloadButton>{ar.pages.offline.retry}</ReloadButton>
      </StatusScreen>
    </div>
  );
}
