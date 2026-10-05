'use client';

import type { Route } from 'next';
import { ScanSweep } from '@/components/fx/scan-sweep';
import { PhotoPlaceholder } from '@/components/insight/photo-placeholder';
import { ScenePhoto, type ScenePoint } from '@/components/insight/scene-photo';
import { SoundToggle } from '@/components/ui/sound-toggle';
import { apiUrl, type Scan } from '@/lib/scan/api';
import { messages } from '@/messages';
import { FocusStage } from './focus-picker';

export interface ScanStageProps {
  /** Null while the scan is being read. */
  scan: Scan | null;
  /** A run is in progress: the photo is swept by a light, and nothing can be chosen on it. */
  running: boolean;
  /** The scene has a sound: a speaker in the photo's corner says so, and silences it in one tap. */
  sound?: boolean;
  /** The reader is choosing what to focus on. */
  focusing: boolean;
  selectedEntity: string | undefined;
  onSelectEntity: (id: string) => void;
  /** The insights with a place in the photo; their list is the panel's. */
  points: readonly ScenePoint[];
  onSelectPoint: (id: string) => void;
  backHref: Route;
}

/** The photo, only when the API says it may be shown: after the sensitivity verdict, and while it is kept. */
function shownPhoto(scan: Scan | null) {
  if (scan === null || scan.sensitive || !scan.image.available || scan.image.url === null) {
    return null;
  }
  const { width, height, url } = scan.image;
  return width === null || height === null ? null : { src: apiUrl(url), width, height };
}

function placeholderNote(scan: Scan | null, running: boolean): string {
  if (scan?.sensitive) {
    return messages.scan.sensitive;
  }
  return running || scan === null ? messages.scan.photoWaiting : messages.scan.photoGone;
}

/**
 * The stage of the scan screen (DESIGN_DECISION.md «Analysis»): the photo
 * with a sweep of light while the stages run, with the glowing points of its
 * insights once they are ready, or with a box on each thing found while the
 * reader chooses a focus, and with a speaker in its corner when the scene has
 * a sound, ringed while the sound loops. A photo that may not be shown (a sensitive scene) or
 * is not there yet (no verdict) or no longer there is never drawn: a calm
 * panel says which of the three it is.
 */
export function ScanStage({
  scan,
  running,
  sound = false,
  focusing,
  selectedEntity,
  onSelectEntity,
  points,
  onSelectPoint,
  backHref,
}: ScanStageProps) {
  const photo = shownPhoto(scan);
  if (photo === null) {
    return (
      <PhotoPlaceholder
        note={placeholderNote(scan, running)}
        backHref={backHref}
        busy={running && scan?.sensitive !== true}
        fill
      />
    );
  }
  if (focusing) {
    return (
      <FocusStage
        {...photo}
        alt={messages.scan.photoAlt}
        entities={(scan as Scan).entities}
        selectedId={selectedEntity}
        onSelect={onSelectEntity}
      />
    );
  }
  return (
    <ScenePhoto
      {...photo}
      alt={messages.scan.photoAlt}
      points={running ? [] : points}
      onSelect={onSelectPoint}
      unoptimized
      listInPanel
      className="h-full"
    >
      <ScanSweep active={running} />
      {sound ? <SceneSoundBadge live={running} /> : null}
    </ScenePhoto>
  );
}

/** The speaker of a scene with a sound; its ring breathes while the sound loops, never on hover. */
function SceneSoundBadge({ live }: { live: boolean }) {
  return (
    <div className="fx-enter absolute top-3.5 end-3.5 z-10">
      {live ? (
        <span
          aria-hidden="true"
          className="fx-sound-ring pointer-events-none absolute inset-0 rounded-full"
        />
      ) : null}
      <SoundToggle />
    </div>
  );
}
