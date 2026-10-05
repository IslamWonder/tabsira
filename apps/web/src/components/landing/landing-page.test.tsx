import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { forgetSession, setGuest } from '@/account/session';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import type { LandingFeatures } from './landing-model';
import { LandingPage } from './landing-page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/',
}));

const ALL_ON: LandingFeatures = {
  chat: true,
  world: true,
  treasure: true,
  social: true,
  atlas: true,
  cameraDiscovery: true,
  photoStorage: true,
  canonicalVerify: true,
};

function page(features: LandingFeatures = ALL_ON) {
  return render(
    <CaptureProvider>
      <LandingPage features={features} />
    </CaptureProvider>
  );
}

beforeEach(() => {
  mockApi({ 'GET /tutorial/rain': () => new Promise(() => undefined) });
  forgetSession();
});

describe('LandingPage', () => {
  it('places the community box after the steps, never beside the way in', () => {
    render(
      <CaptureProvider>
        <LandingPage features={ALL_ON} community={<section aria-label="community box" />} />
      </CaptureProvider>
    );

    const box = screen.getByRole('region', { name: 'community box' });
    const steps = screen.getByRole('heading', { name: 'من صورةٍ تلتقطها، إلى بصيرةٍ تعيشها.' });
    const stories = screen.getByRole('heading', { name: 'تبدأ بصورة. وتتّسع مع كلّ بصيرة.' });
    expect(steps.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(box.compareDocumentPosition(stories) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('says what TABSIRA does, with its two ways in before the picture', () => {
    setGuest();
    page();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'انظر إلى العالمبعين الوحي.'
    );
    const capture = screen.getByRole('button', { name: 'صوّر مشهدًا' });
    const example = screen.getByRole('link', { name: 'جرّب مثالًا' });
    const picture = screen.getByRole('img', { name: /هاتف يعرض نبتة زيتون/ });
    expect(example).toHaveAttribute('href', '#example');
    // The way in comes before the picture, for a reader and on a phone.
    expect(
      capture.compareDocumentPosition(picture) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByText('ابدأ بمثال جاهز، دون تسجيل أو أذونات.')).toBeInTheDocument();
  });

  it('opens the camera from the hero and from the closing call, and asks nothing before', async () => {
    page();
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'ابدأ بصيرتك الأولى' }));

    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
  });

  it('walks through the three steps, the stories that are on, trust and questions', () => {
    page({ ...ALL_ON, social: false });

    const steps = screen.getByRole('region', { name: 'من صورةٍ تلتقطها، إلى بصيرةٍ تعيشها.' });
    expect(within(steps).getAllByRole('listitem')).toHaveLength(3);
    const stories = screen.getAllByRole('article');
    expect(stories.map((story) => within(story).getByRole('heading').textContent)).toEqual([
      'لكلّ مشهد، حديثٌ معك.',
      'أماكن تعرفها. معانٍ تكتشفها.',
      'بصيرة لك. وأثرٌ يصل لغيرك.',
    ]);
    const community = stories[2] as HTMLElement;
    expect(within(community).queryByText('تبصرة تواصل')).toBeNull();
    expect(within(community).getByRole('link', { name: 'افتح عالمي' })).toHaveAttribute(
      'href',
      '/world'
    );
    expect(
      within(stories[0] as HTMLElement).getByRole('link', { name: 'جرّب بصيرة الآن' })
    ).toHaveAttribute('href', '#example');
    expect(screen.getByRole('region', { name: 'لماذا تبصرة؟' })).toBeInTheDocument();
    const question = screen.getByText('هل أحتاج إلى حساب؟');
    expect(question.closest('details')).not.toHaveAttribute('open');
  });

  it('shows a story with no way in when nothing it leads to is on', () => {
    page({
      chat: false,
      world: false,
      treasure: false,
      social: false,
      atlas: false,
      cameraDiscovery: false,
      photoStorage: true,
      canonicalVerify: false,
    });
    const community = screen.getAllByRole('article')[1] as HTMLElement;
    expect(within(community).queryByRole('link')).toBeNull();
  });

  it('opens and closes the phone menu by touch and keyboard, giving focus back', async () => {
    page();
    const button = screen.getByRole('button', { name: 'القائمة' });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(button);
    const menu = screen.getByRole('navigation', { name: 'أقسام الصفحة' });
    expect(
      within(menu)
        .getAllByRole('link')
        .map((link) => link.getAttribute('href'))
    ).toEqual(['/', '/#how', '/#features', '/#example', '/signin']);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('navigation', { name: 'أقسام الصفحة' })).toBeNull();
    expect(button).toHaveFocus();

    await userEvent.click(button);
    await userEvent.click(screen.getByRole('link', { name: 'كيف تعمل؟' }));
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    await userEvent.keyboard('a');
    await userEvent.click(screen.getByRole('link', { name: 'دخول' }));
    expect(screen.queryByRole('navigation', { name: 'أقسام الصفحة' })).toBeNull();
  });

  it('leaves the sign-in out of the menu for an account', async () => {
    mockApi({
      'GET /tutorial/rain': () => new Promise(() => undefined),
      'GET /auth/me': { body: USER },
    });
    page();
    await userEvent.click(screen.getByRole('button', { name: 'القائمة' }));
    await vi.waitFor(() => expect(screen.queryByRole('link', { name: 'دخول' })).toBeNull());
  });

  it('holds both openings while the session is unknown, the device mark choosing one before paint', () => {
    mockApi({
      'GET /tutorial/rain': () => new Promise(() => undefined),
      'GET /auth/me': () => new Promise(() => undefined),
    });
    const { container } = page();

    // The welcome is hidden by CSS on a device that last saw an account with its own insight,
    // the capture on every other; no flash of the one that does not apply (globals.css).
    const welcome = container.querySelector('.only-without-own-insight');
    const capture = container.querySelector('.only-with-own-insight');
    expect(welcome).toBeInstanceOf(HTMLElement);
    expect(capture).toBeInstanceOf(HTMLElement);
    expect(welcome?.querySelector('#landing-title')).toBeInstanceOf(HTMLElement);
    expect(capture?.querySelector('#landing-own-title')).toBeInstanceOf(HTMLElement);
    expect(container.querySelectorAll('[id="landing-title"]')).toHaveLength(1);
  });

  it('keeps only the welcome for a guest once the session is known', async () => {
    mockApi({
      'GET /tutorial/rain': () => new Promise(() => undefined),
      'GET /auth/me': { status: 401, body: { error: 'UNAUTHORIZED', detail: 'x' } },
    });
    const { container } = page();
    await vi.waitFor(() => expect(container.querySelector('.only-with-own-insight')).toBeNull());
    expect(container.querySelector('.only-without-own-insight')).toBeNull();
    expect(container.querySelector('#landing-title')).not.toBeNull();
  });

  it('gives an account with an insight of its own the capture card, and no example', async () => {
    mockApi({
      'GET /tutorial/rain': () => new Promise(() => undefined),
      'GET /auth/me': { body: { ...USER, has_own_insight: true } },
    });
    const { container } = page();
    // Once the session is known, only the capture is left, and the device remembers it.
    await vi.waitFor(() => expect(container.querySelector('.only-with-own-insight')).toBeNull());
    expect(window.localStorage.getItem('tabsira.own-insight')).toBe('1');

    const card = await screen.findByRole('region', { name: 'صوّر مشهدك أنت' });
    expect(within(card).getByRole('button', { name: 'التقط صورة' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('تبصرة');
    expect(screen.queryByRole('link', { name: 'جرّب مثالًا' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'جرّب بصيرة الآن' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'جرّب بصيرة' })).toBeNull();
    expect(document.getElementById('example')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'القائمة' }));
    const menu = screen.getByRole('navigation', { name: 'أقسام الصفحة' });
    expect(within(menu).queryByRole('link', { name: 'جرّب بصيرة' })).toBeNull();

    await userEvent.click(within(card).getByRole('button', { name: 'التقط صورة' }));
    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
  });

  it('keeps the example for an account without an insight of its own', async () => {
    mockApi({
      'GET /tutorial/rain': () => new Promise(() => undefined),
      'GET /auth/me': { body: USER },
    });
    page();
    await userEvent.click(screen.getByRole('button', { name: 'القائمة' }));
    await vi.waitFor(() => expect(screen.queryByRole('link', { name: 'دخول' })).toBeNull());

    expect(screen.getByRole('link', { name: 'جرّب مثالًا' })).toBeInTheDocument();
    expect(document.getElementById('example')).not.toBeNull();
  });
});
