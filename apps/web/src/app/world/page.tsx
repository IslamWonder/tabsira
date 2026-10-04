import type { Metadata } from 'next';
import { WorldScreen } from '@/components/world/world-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// A personal space: never indexed.
export const metadata: Metadata = unlistedMetadata({
  path: '/world',
  title: messages.nav.world,
});

/** The personal world: a fog map of the learning path, loaded for its owner. */
export default function WorldPage() {
  return <WorldScreen />;
}
