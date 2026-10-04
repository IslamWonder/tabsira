import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { RAIN_POINTS, SceneExperience } from './scene-experience';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

describe('SceneExperience', () => {
  it('opens on the prepared rain photo with its two insights, marked as an example', () => {
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

  it('opens an insight in a sheet that says what will appear there, without any text it cannot verify', async () => {
    render(<SceneExperience />);
    await userEvent.click(document.querySelector('[data-point-id="drop"]') as HTMLElement);
    const sheet = screen.getByRole('dialog', { name: 'الحياة في قطرة' });
    expect(sheet).toHaveAccessibleDescription('كيف تُحيا الأرض بعد موتها');
    expect(within(sheet).getByText(/لا نعرض نصًا قبل أن يأتي من مصدره/)).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps a photo you bring on your device and says so', async () => {
    const createObjectURL = vi.fn(() => 'blob:local');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    render(<SceneExperience />);
    const [panelPicker] = screen.getAllByLabelText('اختر صورة');
    await userEvent.upload(
      panelPicker as HTMLElement,
      new File(['x'], 'mine.jpg', { type: 'image/jpeg' })
    );
    const sheet = screen.getByRole('dialog', { name: 'صورتك' });
    expect(within(sheet).getByRole('img', { name: 'الصورة التي اخترتها' })).toHaveAttribute(
      'src',
      'blob:local'
    );
    expect(within(sheet).getByText(/لم يُرسَل شيء إلى أي مكان/)).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: 'أغلق' }));
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:local');
    vi.unstubAllGlobals();
  });

  it('starts a new scene from the phone overlay, and shows a pasted link without loading it', async () => {
    render(<SceneExperience />);
    await userEvent.click(screen.getByRole('button', { name: 'أو صوّر مشهدك أنت' }));
    const starter = screen.getByRole('dialog', { name: 'صوّر مشهدًا' });
    await userEvent.click(within(starter).getByRole('button', { name: 'الصق رابط صورة' }));
    await userEvent.type(within(starter).getByLabelText('رابط الصورة'), 'example.org/rain.jpg');
    await act(async () => {
      await userEvent.click(within(starter).getByRole('button', { name: 'استخدم الرابط' }));
    });
    const sheet = screen.getByRole('dialog', { name: 'رابط صورتك' });
    expect(within(sheet).getByText('https://example.org/rain.jpg')).toBeInTheDocument();
    expect(within(sheet).queryByRole('img')).toBeNull();
  });

  it('closes the phone starter without choosing anything', async () => {
    render(<SceneExperience />);
    await userEvent.click(screen.getByRole('button', { name: 'أو صوّر مشهدك أنت' }));
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
