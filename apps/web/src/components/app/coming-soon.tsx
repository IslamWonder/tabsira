import { ar } from '@/messages/ar';
import { StatusScreen, type StatusScreenProps } from './status-screen';

/** A route that exists but is not built yet: an honest coming-soon state, no sample data. */
export function ComingSoon(props: Omit<StatusScreenProps, 'badge'>) {
  return <StatusScreen {...props} badge={ar.comingSoon.badge} />;
}
