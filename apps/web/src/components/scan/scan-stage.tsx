'use client';

import type { Route } from 'next';
import type { CSSProperties, ReactNode } from 'react';
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
export function shownPhoto(scan: Scan | null) {
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
}: Readonly<ScanStageProps>) {
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
      <PhotoFrame width={photo.width} height={photo.height}>
        <FocusStage
          {...photo}
          alt={messages.scan.photoAlt}
          entities={(scan as Scan).entities}
          selectedId={selectedEntity}
          onSelect={onSelectEntity}
        />
      </PhotoFrame>
    );
  }
  return (
    <PhotoFrame width={photo.width} height={photo.height}>
      <ScenePhoto
        {...photo}
        alt={messages.scan.photoAlt}
        points={running ? [] : points}
        onSelect={onSelectPoint}
        unoptimized
        listInPanel
        framed
        morph
        className="h-full"
      >
        <ScanSweep active={running} />
        {sound ? <SceneSoundBadge /> : null}
      </ScenePhoto>
    </PhotoFrame>
  );
}

/**
 * The reader's photo, whole. On a phone it fills the top of the screen as
 * before. From tablet up it sits in a frame of its own proportions, as large as
 * the stage allows and never larger: `min(width, height × ratio)` of the stage,
 * read through container units, so a tall photo is not cropped and zoomed to
 * fill a wide column, and the page needs no scroll to see it. Its points keep
 * their places, because the frame has the photo's own ratio.
 */
export function PhotoFrame({
  width,
  height,
  children,
}: Readonly<{
  width: number;
  height: number;
  children: ReactNode;
}>) {
  const ratio = { '--photo-ratio': `${width} / ${height}` } as CSSProperties;
  return (
    <div className="h-full w-full tablet:flex tablet:items-center tablet:justify-center tablet:p-8 tablet:[container-type:size]">
      <div
        style={ratio}
        className="relative h-full w-full tablet:aspect-[var(--photo-ratio)] tablet:h-auto tablet:w-[min(100cqw,calc(100cqh*var(--photo-ratio)))] tablet:overflow-hidden tablet:rounded-[24px] tablet:shadow-[var(--stage-shadow)]"
      >
        {children}
      </div>
    </div>
  );
}

/** The speaker of a scene with a sound; it shows when the sound is heard, never on hover. */
function SceneSoundBadge() {
  return (
    <div className="fx-enter absolute top-3.5 end-3.5 z-10">
      <SoundToggle />
    </div>
  );
}
