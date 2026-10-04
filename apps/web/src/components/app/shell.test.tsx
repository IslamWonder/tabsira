import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { ComingSoon } from './coming-soon';
import { ReloadButton } from './reload-button';
import { ServiceWorkerRegister } from './service-worker-register';
import { SkipLink } from './skip-link';
import { patternFor, StageBackdrop } from './stage-backdrop';
import { StatusScreen } from './status-screen';
import { ThemeSync } from './theme-sync';
import { Wordmark } from './wordmark';

vi.mock('next/navigation', () => ({ usePathname: () => '/atlas' }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SkipLink', () => {
  it('jumps to the main content', () => {
    render(<SkipLink />);
    expect(screen.getByRole('link', { name: 'انتقل إلى المحتوى' })).toHaveAttribute(
      'href',
      '#main'
    );
  });
});

describe('StatusScreen and ComingSoon', () => {
  it('shows one titled message with its actions', () => {
    render(
      <StatusScreen icon={<span />} title="[عنوان]" description="[وصف]" className="extra">
        <button type="button">[فعل]</button>
      </StatusScreen>
    );
    const region = screen.getByRole('region', { name: '[عنوان]' });
    expect(region).toHaveClass('extra');
    expect(screen.getByRole('heading', { level: 1, name: '[عنوان]' })).toBeInTheDocument();
    expect(screen.getByText('[وصف]')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '[فعل]' })).toBeInTheDocument();
  });

  it('says «قريبًا» for a route that is not built yet, at the heading level asked', () => {
    render(<ComingSoon icon={<span />} title="[عنوان]" description="[وصف]" headingLevel={2} />);
    expect(screen.getByText('قريبًا')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '[عنوان]' })).toBeInTheDocument();
  });
});

describe('ReloadButton', () => {
  it('reloads the page', async () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    render(<ReloadButton>أعد المحاولة</ReloadButton>);
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(reload).toHaveBeenCalledOnce();
  });
});

describe('ServiceWorkerRegister', () => {
  function stubServiceWorker(register: ReturnType<typeof vi.fn>) {
    Object.defineProperty(navigator, 'serviceWorker', { value: { register }, configurable: true });
  }

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'serviceWorker');
  });

  it('registers the worker for the whole site when enabled', () => {
    const register = vi.fn().mockResolvedValue({});
    stubServiceWorker(register);
    render(<ServiceWorkerRegister enabled />);
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/', updateViaCache: 'none' });
  });

  it('shrugs off a failed registration', async () => {
    const register = vi.fn().mockRejectedValue(new Error('denied'));
    stubServiceWorker(register);
    render(<ServiceWorkerRegister enabled />);
    await Promise.resolve();
    expect(register).toHaveBeenCalledOnce();
  });

  it('stays off in development and where workers are not supported', () => {
    const register = vi.fn();
    stubServiceWorker(register);
    render(<ServiceWorkerRegister />);
    expect(register).not.toHaveBeenCalled();
    Reflect.deleteProperty(navigator, 'serviceWorker');
    expect(() => render(<ServiceWorkerRegister enabled />)).not.toThrow();
  });
});

describe('ThemeSync', () => {
  it('applies the stored theme once mounted', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(<ThemeSync />);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});

describe('Wordmark and StageBackdrop', () => {
  it('writes the name with its point hidden from screen readers', () => {
    const { container } = render(<Wordmark className="extra" />);
    expect(container.textContent).toBe('تَبْصِرَة.');
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe('.');
  });

  it('draws a decorative living stage with the tiling of the screen', () => {
    const { container } = render(<StageBackdrop />);
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelectorAll('.fx-aurora__blob')).toHaveLength(3);
    expect(container.querySelector('[data-pattern]')).toHaveAttribute('data-pattern', '12');
  });

  it('gives each screen its tiling', () => {
    expect(patternFor('/atlas')).toBe(12);
    expect(patternFor('/world/oasis')).toBe(6);
    expect(patternFor('/')).toBe(8);
  });
});
