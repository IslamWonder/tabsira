import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { insightOut, scanOut, tutorialOut } from '@/test/scan';
import { RAIN_POINTS, SceneExperience } from './scene-experience';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push }),
}));

beforeEach(() => {
  push.mockClear();
});

const tutorial: Record<string, Route> = { 'GET /tutorial/rain': { body: tutorialOut() } };

const image = () => new File(['x'], 'mine.jpg', { type: 'image/jpeg' });

describe('SceneExperience: the prepared example', () => {
  it('opens on the rain photo with its two insights at once, before the API answers, marked as an example', () => {
    render(<SceneExperience />);
    expect(
      screen.getByRole('img', { name: 'نبتة زيتون صغيرة تتلقى قطرات المطر' })
    ).toBeInTheDocument();
    expect(RAIN_POINTS.map((point) => point.title)).toEqual([
      'الحياة في قطرة',
      'الغرس الذي يتعدّاك',
    ]);
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(2);
    expect(screen.getAllByText('مثال موثّق مُعدّ').length).toBeGreaterThan(0);
  });

  it('takes the titles, places, label and description of the photo from the API when they arrive', async () => {
    mockApi(tutorial);
    render(<SceneExperience />);
    expect(await screen.findByRole('img', { name: 'نبتة تتلقى المطر' })).toBeInTheDocument();
    expect(document.querySelector('[data-point-id="drop"]')).not.toBeNull();
    expect(screen.getAllByText('كيف تُحيا الأرض').length).toBeGreaterThan(0);
  });

  it('keeps the example as it is when the API does not answer', async () => {
    mockApi({ 'GET /tutorial/rain': apiError(503, 'SERVICE_UNAVAILABLE') });
    render(<SceneExperience />);
    await act(async () => undefined);
    expect(document.querySelectorAll('[data-point-id]')).toHaveLength(2);
  });

  it('opens the API copy of an insight and goes to it', async () => {
    const api = mockApi({
      ...tutorial,
      'POST /tutorial/rain/insights/drop': { body: insightOut({ id: '110000000000000077' }) },
    });
    render(<SceneExperience />);
    await userEvent.click(document.querySelector('[data-point-id="drop"]') as HTMLElement);
    expect(push).toHaveBeenCalledWith('/insight/110000000000000077');
    expect(api.requests.filter((request) => request.method === 'POST')).toHaveLength(1);
  });

  it('opens it from the list too, once, however many times it is tapped', async () => {
    mockApi({
      ...tutorial,
      'POST /tutorial/rain/insights/drop': {
        body: insightOut({ id: '110000000000000077' }),
      },
    });
    render(<SceneExperience />);
    const row = within(screen.getByRole('region', { name: 'المس البصيرة التي لفتتك' })).getByRole(
      'button',
      { name: /الحياة في قطرة/ }
    );
    await userEvent.dblClick(row);
    expect(push).toHaveBeenCalledTimes(1);
    expect(screen.getByText('أفتح البصيرة…')).toBeInTheDocument();
  });

  it('says why an insight could not be opened, and lets the reader tap again', async () => {
    mockApi({ ...tutorial, 'POST /tutorial/rain/insights/drop': 'network-error' });
    render(<SceneExperience />);
    await userEvent.click(document.querySelector('[data-point-id="drop"]') as HTMLElement);
    expect(await screen.findByText(/تعذّر الوصول إلى تبصرة/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByText('أفتح البصيرة…')).toBeNull();
  });
});

describe('SceneExperience: a scene of the reader', () => {
  it('says before anything is sent that the photo goes to the AI provider', () => {
    render(<SceneExperience />);
    expect(screen.getAllByText(/تُرسل صورتك إلى مزوّد الذكاء الاصطناعي/).length).toBeGreaterThan(0);
  });

  it('sends the photo, never shows it back, and goes to the scan', async () => {
    const api = mockApi({
      ...tutorial,
      'POST /scans': { status: 202, body: scanOut({ id: '110000000000000099', status: 'queued' }) },
    });
    render(<SceneExperience />);
    const [picker] = screen.getAllByLabelText('اختر صورة');
    await userEvent.upload(picker as HTMLElement, image());
    expect(push).toHaveBeenCalledWith('/scan/110000000000000099');
    expect(screen.queryByRole('img', { name: 'الصورة التي اخترتها' })).toBeNull();
    expect(api.requests.some((request) => request.url.endsWith('/scans'))).toBe(true);
  });

  it('says in Arabic why the API refused the photo, and offers to try again or to close', async () => {
    let answers = 0;
    mockApi({
      ...tutorial,
      'POST /scans': () => {
        answers += 1;
        return answers === 1
          ? apiError(415, 'IMAGE_UNSUPPORTED')
          : { status: 202, body: scanOut({ id: '110000000000000097', status: 'queued' }) };
      },
    });
    render(<SceneExperience />);
    const [picker] = screen.getAllByLabelText('اختر صورة');
    await userEvent.upload(picker as HTMLElement, image());
    const sheet = await screen.findByRole('dialog', { name: 'صورتك' });
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('هذه الصيغة غير مدعومة');
    await userEvent.click(within(sheet).getByRole('button', { name: 'أعد المحاولة' }));
    expect(push).toHaveBeenCalledWith('/scan/110000000000000097');
  });

  it('shows what is being sent, and leaving drops the answer that comes late', async () => {
    let release: () => void = () => undefined;
    mockApi({
      ...tutorial,
      'POST /scans': () =>
        new Promise((resolve) => {
          release = () => resolve({ status: 202, body: scanOut({ status: 'queued' }) });
        }),
    });
    render(<SceneExperience />);
    const [picker] = screen.getAllByLabelText('اختر صورة');
    await userEvent.upload(picker as HTMLElement, image());
    const sheet = screen.getByRole('dialog', { name: 'صورتك' });
    expect(within(sheet).getByRole('status')).toHaveTextContent('جارٍ إرسال صورتك لتحليلها…');
    // The phone's file name says nothing to the reader.
    expect(sheet).not.toHaveTextContent('mine.jpg');
    await userEvent.click(within(sheet).getByRole('button', { name: 'ألغِ' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    await act(async () => release());
    expect(push).not.toHaveBeenCalled();
  });

  it('closes the phone starter without choosing anything', async () => {
    render(<SceneExperience />);
    await userEvent.click(screen.getByRole('button', { name: 'أو صوّر مشهدك أنت' }));
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
