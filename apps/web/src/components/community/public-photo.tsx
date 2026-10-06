'use client';

import { useState } from 'react';
import { cx } from '@/lib/cx';

export interface PublicPhotoProps {
  url: string | null;
  alt: string;
  /** `full` shows the whole photo on its own page; `thumb` crops a medium strip for a list. */
  size?: 'full' | 'thumb';
  className?: string;
}

/**
 * The public copy of an insight's photo, shown exactly where its owner chose to
 * show it: a published public post or a published atlas entry (v2 §19). The API
 * gives an absolute address under the configured public base (`photo_url`) or
 * nothing; a plain `<img>` loads it, lazily, from that host alone, and anything
 * that is not an http(s) address is not rendered at all. The request carries no referrer, so a
 * photo served by another host (decision 66, placepix.net) never learns which page asked for it.
 * One frame for both sizes: a thin gilded mat around the picture, no glow. A photo that fails to
 * load leaves no broken frame behind. Hover changes nothing.
 */
export function PublicPhoto({ url, alt, size = 'full', className }: Readonly<PublicPhotoProps>) {
  const [failed, setFailed] = useState(false);
  if (failed || url === null || !/^https?:\/\//.test(url)) {
    return null;
  }
  return (
    <figure
      className={cx(
        'm-0 rounded-[var(--radius-card)] border border-primary/30 bg-surface p-1.5',
        className
      )}
    >
      {/* The API's address is the source of truth; Next's image loader would add a request path of its own. */}
      {/* biome-ignore lint/performance/noImgElement: a plain img keeps the only request on the configured host. */}
      <img
        src={url}
        alt={alt}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={cx(
          'block w-full rounded-[calc(var(--radius-card)-6px)] bg-canvas',
          size === 'full' ? 'max-h-[70vh] object-contain' : 'h-44 object-cover tablet:h-56'
        )}
        data-testid="public-photo"
      />
    </figure>
  );
}
