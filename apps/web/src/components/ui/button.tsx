import type { Route } from 'next';
import Link from 'next/link';
import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react';
import { cx } from '@/lib/cx';

export type ButtonVariant = 'primary' | 'cta' | 'secondary' | 'ghost' | 'icon';
export type ButtonSize = 'md' | 'lg';

/*
 * Every target is at least 48 px high (the product's own rule, tajriba §10).
 * Hover changes colour only, never position or size (AGENTS.md); a press is an
 * event, so it may answer with a slight settle, and only when motion is allowed.
 */
const BASE =
  'inline-flex select-none items-center justify-center gap-2 rounded-full font-medium ' +
  'transition-[background-color,color,border-color,box-shadow,filter] duration-200 ' +
  'motion-safe:active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ' +
  'aria-disabled:cursor-not-allowed aria-disabled:opacity-50';

const VARIANTS: Record<ButtonVariant, string> = {
  // Von Restorff: one glowing fill per screen marks the action that matters.
  primary: 'fill-primary font-heading font-bold hover:brightness-110',
  // The call to capture a scene: gold by day, the glowing emerald by night.
  cta: 'fill-cta font-heading font-bold hover:brightness-105',
  secondary:
    'border-[1.5px] border-[var(--secondary-border)] bg-[var(--secondary-bg)] text-[var(--secondary-fg)] ' +
    'hover:bg-surface',
  ghost: 'bg-transparent text-fg-soft hover:text-fg',
  icon: 'glass text-fg hover:text-primary',
};

const SIZES: Record<ButtonSize, Record<ButtonVariant, string>> = {
  md: {
    primary: 'min-h-12 px-6 text-[1.0625rem]',
    cta: 'min-h-12 px-6 text-[1.0625rem]',
    secondary: 'min-h-12 px-5 text-[0.9375rem]',
    ghost: 'min-h-12 px-4 text-[0.9375rem]',
    icon: 'size-12',
  },
  lg: {
    // Fitts: the closing action of a screen is the widest, tallest target in the thumb zone.
    primary: 'min-h-14 px-8 text-[1.25rem]',
    cta: 'min-h-14 px-8 text-[1.25rem]',
    secondary: 'min-h-14 px-6 text-base',
    ghost: 'min-h-14 px-5 text-base',
    icon: 'size-14',
  },
};

export function buttonClasses(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  className?: string
): string {
  return cx(BASE, VARIANTS[variant], SIZES[size][variant], className);
}

type NativeButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'children' | 'aria-label'
> & {
  ref?: Ref<HTMLButtonElement>;
};

interface TextButtonProps extends NativeButtonProps {
  variant?: Exclude<ButtonVariant, 'icon'>;
  size?: ButtonSize;
  children: ReactNode;
}

interface IconButtonProps extends NativeButtonProps {
  variant: 'icon';
  size?: ButtonSize;
  /** The accessible name; an icon alone has none. */
  label: string;
  /** The icon, decorative. */
  children: ReactNode;
}

export type ButtonProps = TextButtonProps | IconButtonProps;

export function Button(props: ButtonProps) {
  if (props.variant === 'icon') {
    const { variant, size, label, children, className, type = 'button', ...rest } = props;
    return (
      <button
        type={type}
        aria-label={label}
        className={buttonClasses(variant, size, className)}
        {...rest}
      >
        <span aria-hidden="true" className="contents">
          {children}
        </span>
      </button>
    );
  }
  const { variant, size, children, className, type = 'button', ...rest } = props;
  return (
    <button type={type} className={buttonClasses(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

interface LinkButtonProps {
  href: Route;
  variant?: Exclude<ButtonVariant, 'icon'>;
  size?: ButtonSize;
  /** The page it leads to is the one being shown. */
  current?: boolean;
  className?: string;
  children: ReactNode;
}

/** A link that looks like a button: for actions that navigate. */
export function LinkButton({ href, variant, size, current, className, children }: LinkButtonProps) {
  return (
    <Link
      href={href}
      aria-current={current ? 'page' : undefined}
      className={buttonClasses(variant, size, className)}
    >
      {children}
    </Link>
  );
}
