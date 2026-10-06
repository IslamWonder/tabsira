import type { Route } from 'next';
import Link from 'next/link';
import { LogoMark } from '@/components/brand/logo';
import { ScanSweep } from '@/components/fx/scan-sweep';
import { SummoningCircle } from '@/components/fx/summoning-circle';
import { SoundToggle } from '@/components/ui/sound-toggle';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { BackArrow } from './insight-frame';

export interface PhotoPlaceholderProps {
  note: string;
  /** Where the round way back leads, as it does on a photo; omitted where the page has its own. */
  backHref?: Route;
  /** Fills the stage it is in (the scan screen) instead of the fixed height of the insight's photo. */
  fill?: boolean;
  /**
   * The scan is running: the summoning circle turns where the photo will be, and a band of
   * light sweeps the stage, so the wait for the verdict reads as work being done, not as a gap.
   */
  busy?: boolean;
  className?: string;
}

/**
 * Stands where the photo would be when it must not or cannot be shown: a
 * sensitive scene (never shown back, never kept), a photo that left the
 * temporary store, or a scan whose verdict is not in yet. It says why in a
 * sentence, so the empty place is never a mystery (tajriba §8).
 */
export function PhotoPlaceholder({
  note,
  backHref,
  fill = false,
  busy = false,
  className,
}: Readonly<PhotoPlaceholderProps>) {
  return (
    <div
      className={cx(
        'photo-scrim relative flex w-full flex-col items-center justify-center gap-3 px-8 text-center',
        fill
          ? 'h-full min-h-[240px]'
          : 'h-[330px] tablet:h-[420px] desktop:h-[min(720px,calc(var(--app-height)-var(--topbar-height)-6rem))] desktop:rounded-[28px]',
        className
      )}
    >
      {backHref === undefined ? null : (
        <SoundToggle className="absolute top-3.5 end-3.5 z-10 tablet:hidden" />
      )}
      {backHref === undefined ? null : (
        <Link
          href={backHref}
          aria-label={messages.insight.back}
          className="glass absolute top-3.5 start-3.5 z-10 inline-flex size-12 items-center justify-center rounded-full text-glass-fg desktop:hidden"
        >
          <BackArrow />
        </Link>
      )}
      {busy ? <SummoningCircle active size={132} /> : <LogoMark className="h-16 opacity-80" />}
      <p className="m-0 max-w-xs text-[0.9375rem] text-fg-soft leading-[1.8]">{note}</p>
      <ScanSweep active={busy} />
    </div>
  );
}
