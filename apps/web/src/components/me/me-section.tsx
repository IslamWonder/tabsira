import { type ReactNode, useId } from 'react';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';

export interface MeSectionProps {
  /** The anchor the section list links to. */
  id: string;
  title: string;
  /** One line on what the section holds, under its title. */
  description?: string;
  className?: string;
  children: ReactNode;
}

/** One part of the profile page: a glass window with its own heading (Law of Common Region). */
export function MeSection({ id, title, description, className, children }: MeSectionProps) {
  const titleId = useId();
  return (
    <GlassPanel
      as="section"
      id={id}
      aria-labelledby={titleId}
      className={cx('flex scroll-mt-28 flex-col gap-5 tablet:p-7', className)}
    >
      <header className="flex flex-col gap-1">
        <h2 id={titleId} className="m-0 text-subheading text-fg">
          {title}
        </h2>
        {description === undefined ? null : (
          <p className="m-0 text-fg-soft text-[0.9375rem] leading-[1.85]">{description}</p>
        )}
      </header>
      {children}
    </GlassPanel>
  );
}

/** A quiet sub-heading inside a section: on this device, in your account. */
export function SubHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="m-0 border-line border-b pb-2 font-medium text-fg-muted text-sm">{children}</h3>
  );
}
