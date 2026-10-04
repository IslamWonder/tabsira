import type { Metadata } from 'next';
import { StatusScreen } from '@/components/app/status-screen';
import { LinkButton } from '@/components/ui/button';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.pages.notFound.title,
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <div className="pt-[max(40px,env(safe-area-inset-top))] pb-6">
      <StatusScreen
        emblem="logo"
        title={messages.pages.notFound.title}
        description={messages.pages.notFound.description}
      >
        <LinkButton href="/">{messages.pages.notFound.action}</LinkButton>
      </StatusScreen>
    </div>
  );
}
