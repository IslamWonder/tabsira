'use client';

import { type CSSProperties, type ReactNode, useState } from 'react';
import { useBoxSize } from '@/lib/use-box-size';

export type Viewport = 'phone' | 'tablet' | 'desktop';

const WIDTH: Record<Viewport, number> = { phone: 375, tablet: 834, desktop: 1440 };

export interface ViewportPreviewProps {
  viewport: Viewport;
  theme: 'light' | 'dark';
  label: string;
  /** Height of the simulated screen, in CSS pixels. */
  height: number;
  children: ReactNode;
}

/**
 * A screen of the given size, scaled down to fit. The `tablet:` and
 * `desktop:` variants answer to [data-viewport] (globals.css), so the real
 * components lay themselves out as they would on that device; the transform
 * keeps their fixed parts (the phone bar) inside the frame. Inert: a picture
 * of the shell, not a second copy to tab through.
 */
export function ViewportPreview({
  viewport,
  theme,
  label,
  height,
  children,
}: Readonly<ViewportPreviewProps>) {
  const [outer, setOuter] = useState<HTMLDivElement | null>(null);
  const size = useBoxSize(outer);
  const width = WIDTH[viewport];
  const scale = size === null || size.width === 0 ? 1 : Math.min(1, size.width / width);
  const screen: CSSProperties & Record<'--app-height', string> = {
    width,
    height,
    transform: `scale(${scale})`,
    transformOrigin: 'top right',
    '--app-height': `${height}px`,
  };
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-2">
      <figcaption className="text-fg-soft text-sm">{label}</figcaption>
      <div
        ref={setOuter}
        className="w-full overflow-hidden rounded-[18px] border border-line"
        style={{ height: height * scale }}
      >
        <div
          data-viewport={viewport}
          data-theme={theme}
          inert
          className="stage-aurora relative overflow-hidden"
          style={screen}
        >
          {children}
        </div>
      </div>
    </figure>
  );
}
