import { messages } from '@/messages';
import { StatusScreen, type StatusScreenProps } from './status-screen';

/** A route that exists but is not built yet: an honest coming-soon state, no sample data. */
export function ComingSoon(props: Readonly<Omit<StatusScreenProps, 'badge'>>) {
  return <StatusScreen {...props} badge={messages.comingSoon.badge} />;
}
