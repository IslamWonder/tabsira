import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readSession, setSignedIn } from '@/account/session';
import { apiError, mockApi } from '@/test/api';
import { forgetDevice, stubCamera } from '@/test/camera';
import { USER } from '@/test/fixtures';
import { scanOut } from '@/test/scan';
import { CaptureProvider, useCapture } from './capture-provider';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/world',
}));

/** A page with one «صوّر مشهدًا» of its own, as the bars and the scene have. */
function Opener() {
  const capture = useCapture();
  return (
    <button type="button" onClick={capture.open}>
      صوّر مشهدًا
    </button>
  );
}

beforeEach(() => {
  push.mockClear();
});

afterEach(() => {
  forgetDevice();
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  vi.restoreAllMocks();
});

describe('CaptureProvider', () => {
  it('opens on the live camera at once, with the file picker beside it', async () => {
    const { getUserMedia } = stubCamera('granted');
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    expect(getUserMedia).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));

    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    expect(await within(sheet).findByLabelText('معاينة الكاميرا')).toBeInTheDocument();
    expect(within(sheet).getByLabelText('اختر صورة')).toBeInTheDocument();
  });

  it('asks for no camera on a page that is not secure, and says why', async () => {
    const { getUserMedia } = stubCamera('granted');
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));

    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    expect(within(sheet).getByRole('status')).toHaveTextContent('HTTPS');
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('sends a photo, closes what it opened and goes to the scan', async () => {
    mockApi({
      'POST /scans': { status: 202, body: scanOut({ id: '110000000000000055', status: 'queued' }) },
    });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });

    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/scan/110000000000000055'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('sends a guest who used their one scan to sign-up, back to this page, with the reason', async () => {
    mockApi({ 'POST /scans': apiError(403, 'account_required') });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });

    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/signup?next=%2Fworld&reason=scan'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens the profile form when the API says the profile is not complete', async () => {
    setSignedIn(USER);
    mockApi({ 'POST /scans': apiError(403, 'profile_required') });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });

    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));

    await waitFor(() =>
      expect(readSession()).toMatchObject({ user: { profile_completed: false } })
    );
    expect(push).not.toHaveBeenCalled();
  });

  it('offers the prepared example as the third way in, and closes on the way', async () => {
    stubCamera('granted');
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));
    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    const example = within(sheet).getByRole('link', { name: 'جرّب مثالًا' });
    expect(example).toHaveAttribute('href', '/#example');

    await userEvent.click(example);

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('offers no example to an account that holds an insight of its own', async () => {
    stubCamera('granted');
    setSignedIn({ ...USER, has_own_insight: true });
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));
    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });

    expect(within(sheet).queryByRole('link', { name: 'جرّب مثالًا' })).toBeNull();
  });

  it('opens the camera from the installed app shortcut and leaves a clean address', async () => {
    stubCamera('granted');
    window.history.replaceState(null, '', '/?capture=1&from=icon');
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
    expect(`${window.location.pathname}${window.location.search}`).toBe('/?from=icon');
    window.history.replaceState(null, '', '/');
  });

  it('says a refusal, offers to send the same photo again, and goes on when it works', async () => {
    let answers = 0;
    mockApi({
      'POST /scans': () =>
        answers++ === 0
          ? apiError(500, 'server_error')
          : { status: 202, body: scanOut({ id: '110000000000000077', status: 'queued' }) },
    });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });

    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));

    const sheet = await screen.findByRole('dialog', { name: 'صورتك' });
    expect(await within(sheet).findByRole('alert')).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'أعد المحاولة' }));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/scan/110000000000000077'));
  });

  it("leaves the sending sheet on the reader's word, with nothing left of the failure", async () => {
    mockApi({ 'POST /scans': apiError(500, 'server_error') });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });
    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));
    const sheet = await screen.findByRole('dialog', { name: 'صورتك' });
    await within(sheet).findByRole('alert');

    await userEvent.click(within(sheet).getByRole('button', { name: 'عد إلى المشهد' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it('drops the answer of a photo the reader cancelled while it travelled', async () => {
    let release: () => void = () => undefined;
    mockApi({
      'POST /scans': async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return { status: 202, body: scanOut({ id: '110000000000000088', status: 'queued' }) };
      },
    });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });
    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));
    const sheet = await screen.findByRole('dialog', { name: 'صورتك' });

    await userEvent.click(within(sheet).getByRole('button', { name: 'ألغِ' }));
    await act(async () => release());

    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes the capture sheet with Escape', async () => {
    stubCamera('granted');
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));
    await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('is needed by every page that captures', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => renderHook(() => useCapture())).toThrow('outside a CaptureProvider');
  });
});
