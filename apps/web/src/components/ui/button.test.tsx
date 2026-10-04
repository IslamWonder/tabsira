import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ShareIcon } from '@/components/icons';
import { Button, buttonClasses, LinkButton } from './button';

describe('Button', () => {
  it('is a real button that does not submit forms by default', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>تمّ</Button>);
    const button = screen.getByRole('button', { name: 'تمّ' });
    expect(button).toHaveAttribute('type', 'button');
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('glows as the primary action and keeps 48 px targets in every variant', () => {
    expect(buttonClasses()).toContain('fill-primary');
    expect(buttonClasses('cta')).toContain('fill-cta');
    for (const variant of ['primary', 'cta', 'secondary', 'ghost'] as const) {
      expect(buttonClasses(variant, 'md')).toContain('min-h-12');
      expect(buttonClasses(variant, 'lg')).toContain('min-h-14');
    }
    expect(buttonClasses('icon', 'md')).toContain('size-12');
    expect(buttonClasses('icon', 'lg')).toContain('size-14');
  });

  it('never moves on hover', () => {
    for (const variant of ['primary', 'secondary', 'ghost', 'icon'] as const) {
      expect(buttonClasses(variant)).not.toMatch(/hover:(-?translate|scale|rotate)/);
    }
  });

  it('names an icon-only button by its label and hides the icon', () => {
    render(
      <Button variant="icon" label="شارك البصيرة" type="submit" className="extra">
        <ShareIcon />
      </Button>
    );
    const button = screen.getByRole('button', { name: 'شارك البصيرة' });
    expect(button).toHaveAttribute('type', 'submit');
    expect(button).toHaveClass('glass', 'extra');
    expect(button.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });

  it('can be disabled', () => {
    render(
      <Button variant="secondary" size="lg" disabled>
        غير متاح
      </Button>
    );
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

describe('LinkButton', () => {
  it('navigates with a link styled as a button', () => {
    render(
      <LinkButton href="/world" variant="ghost">
        عالمي
      </LinkButton>
    );
    const link = screen.getByRole('link', { name: 'عالمي' });
    expect(link).toHaveAttribute('href', '/world');
    expect(link.className).toContain('min-h-12');
  });
});
