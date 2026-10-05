import { messages } from '@/messages';

/** First stop of the keyboard: straight to the content, past the navigation. */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="glass sr-only z-50 rounded-full font-medium text-glass-fg focus:not-sr-only focus:px-5 focus:py-3 focus:fixed focus:top-[max(12px,env(safe-area-inset-top))] focus:start-3"
    >
      {messages.a11y.skipToContent}
    </a>
  );
}
