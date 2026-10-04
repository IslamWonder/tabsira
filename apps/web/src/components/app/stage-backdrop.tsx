'use client';

import { usePathname } from 'next/navigation';
import { GeometricPattern, type PatternKind } from '@/components/fx/geometric-pattern';
import { LightMotes } from '@/components/fx/light-motes';

/** Each screen its own tiling: twelve points on the atlas, six on the world, the khatam elsewhere. */
export function patternFor(pathname: string): PatternKind {
  if (pathname.startsWith('/atlas')) {
    return 12;
  }
  return pathname.startsWith('/world') ? 6 : 8;
}

/**
 * The living stage behind every screen (DESIGN_DECISION.md «Game feel»): a
 * night aurora in dark and a dawn aurora in light, three slow clouds of light
 * drifting, the screen's khatam tiling at very low opacity, still stars at
 * night, slow light motes, a film grain and a vignette. No parallax and nothing
 * follows the pointer. Fixed and never transformed (a transformed ancestor
 * would break the fixed navigation); everything stops under reduced motion.
 */
export function StageBackdrop() {
  const pathname = usePathname();
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10">
      <div className="fx-aurora">
        <div className="fx-aurora__blob fx-aurora__blob--a" />
        <div className="fx-aurora__blob fx-aurora__blob--b" />
        <div className="fx-aurora__blob fx-aurora__blob--c" />
        <GeometricPattern kind={patternFor(pathname)} />
        <div className="stage-stars absolute inset-0" />
        <LightMotes />
        <div className="fx-aurora__grain" />
        <div className="fx-aurora__vignette" />
      </div>
    </div>
  );
}
