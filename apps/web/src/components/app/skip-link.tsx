import { ar } from '@/messages/ar';

/** First stop of the keyboard: straight to the content, past the navigation. */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="glass sr-only z-50 rounded-full px-5 py-3 font-medium text-glass-fg focus:not-sr-only focus:fixed focus:top-[max(12px,env(safe-area-inset-top))] focus:right-3"
    >
      {ar.a11y.skipToContent}
    </a>
  );
}
