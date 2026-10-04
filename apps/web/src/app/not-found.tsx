import type { Metadata } from 'next';
import { StatusScreen } from '@/components/app/status-screen';
import { SparkIcon } from '@/components/icons';
import { LinkButton } from '@/components/ui/button';
import { ar } from '@/messages/ar';

export const metadata: Metadata = {
  title: ar.pages.notFound.title,
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-nav">
      <StatusScreen
        icon={<SparkIcon width="28" height="28" />}
        title={ar.pages.notFound.title}
        description={ar.pages.notFound.description}
      >
        <LinkButton href="/">{ar.pages.notFound.action}</LinkButton>
      </StatusScreen>
    </div>
  );
}
