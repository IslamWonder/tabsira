'use client';

import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CloseIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { useModal } from '@/components/ui/use-modal';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export interface PublicPhotoProps {
  url: string | null;
  alt: string;
  /** `full` shows the whole photo on its own page; `thumb` crops a medium strip for a list. */
  size?: 'full' | 'thumb';
  className?: string;
}

/**
 * The photo full screen on a dark ground, as photo apps open one: a tap
 * anywhere, Escape or the close button brings the page back, and focus returns
 * to the photo that opened it (useModal).
 */
function PhotoViewer({
  url,
  alt,
  onClose,
}: Readonly<{ url: string; alt: string; onClose: () => void }>) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useModal(true, rootRef, panelRef, { onEscape: onClose });
  return createPortal(
    <div ref={rootRef} className="fixed inset-0 z-[80]">
      {/* A tap anywhere closes, as in a photo app; hidden from assistive technology, where Escape and the close button do. */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 bg-[rgba(4,10,8,0.94)] motion-safe:animate-fade-in"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={alt}
        tabIndex={-1}
        className="pointer-events-none relative flex size-full items-center justify-center p-3"
      >
        {/* biome-ignore lint/performance/noImgElement: the same address as the page's photo, already loaded. */}
        <img
          src={url}
          alt={alt}
          referrerPolicy="no-referrer"
          className="max-h-full max-w-full rounded-[12px] object-contain"
        />
        <Button
          variant="icon"
          label={messages.sheet.close}
          onClick={onClose}
          className="pointer-events-auto absolute end-4 top-[max(16px,env(safe-area-inset-top))]"
        >
          <CloseIcon />
        </Button>
      </div>
    </div>,
    document.body
  );
}

/**
 * The public copy of an insight's photo, shown exactly where its owner chose to
 * show it: a published public post or a published atlas entry (v2 §19). The API
 * gives an absolute address under the configured public base (`photo_url`) or
 * nothing; a plain `<img>` loads it, lazily, from that host alone, and anything
 * that is not an http(s) address is not rendered at all. The request carries no referrer, so a
 * photo served by another host (decision 66, placepix.net) never learns which page asked for it.
 * One frame for both sizes: a thin gilded mat around the picture, no glow. The whole photo
 * opens full screen on a tap. A photo that fails to load leaves no broken frame behind.
 * Hover changes nothing.
 */
export function PublicPhoto({ url, alt, size = 'full', className }: Readonly<PublicPhotoProps>) {
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  if (failed || url === null || !/^https?:\/\//.test(url)) {
    return null;
  }
  const image = (
    // The API's address is the source of truth; Next's image loader would add a request path of its own.
    // biome-ignore lint/performance/noImgElement: a plain img keeps the only request on the configured host.
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
  );
  return (
    <figure
      className={cx(
        'm-0 rounded-[var(--radius-card)] border border-primary/30 bg-surface p-1.5',
        className
      )}
    >
      {size === 'full' ? (
        <button
          type="button"
          aria-haspopup="dialog"
          aria-label={messages.photoView.open(alt)}
          onClick={() => setOpen(true)}
          className="block w-full cursor-zoom-in rounded-[calc(var(--radius-card)-6px)]"
        >
          {image}
        </button>
      ) : (
        image
      )}
      {open ? <PhotoViewer url={url} alt={alt} onClose={() => setOpen(false)} /> : null}
    </figure>
  );
}
