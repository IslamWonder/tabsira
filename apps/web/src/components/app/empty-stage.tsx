import type { ReactNode } from 'react';
import { GeometricPattern } from '@/components/fx/geometric-pattern';
import { Beacon } from './beacon';

/**
 * The place a photo or a map will fill, shown empty and calm until that
 * feature is built: no sample photo, no invented places (AGENTS.md).
 */
export function EmptyStage({ icon }: { icon: ReactNode }) {
  return (
    <div className="relative flex h-full min-h-72 items-center justify-center overflow-hidden bg-surface">
      <GeometricPattern />
      <Beacon>{icon}</Beacon>
    </div>
  );
}
