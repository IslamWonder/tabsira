import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { USER } from '@/test/fixtures';
import { IDENTITY } from '@/test/social';
import { AccessNote, BlockSheet, ReportSheet, WithdrawSheet } from './sheets';

vi.mock('next/navigation', () => ({ usePathname: () => '/posts/1' }));

const POST_ID = '7345678901234567890';

function member(routes: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /auth/me': { body: USER },
    'GET /me/public-identity': { body: IDENTITY },
    ...routes,
  });
}

describe('AccessNote', () => {
  it('tells an unverified account the step it misses, with no link', () => {
    render(<AccessNote access="unverified" guest="[زائر]" unverified="[أكّد]" />);
    expect(screen.getByText('[أكّد]')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('says nothing to a member, nor about an identity when the action needs none', () => {
    const { container } = render(
      <AccessNote access="no-identity" guest="[زائر]" unverified="[أكّد]" />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('ReportSheet', () => {
  it('sends the chosen reason with trimmed details and confirms', async () => {
    const api = member({ 'POST /reports': { status: 201, body: { id: '1' } } });
    render(<ReportSheet open onClose={() => {}} targetType="post" targetId={POST_ID} />);
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'أرسل البلاغ' })).toBeEnabled()
    );
    await userEvent.click(within(dialog).getByLabelText('محتوى مزعج أو إعلاني'));
    await userEvent.type(
      within(dialog).getByLabelText('تفاصيل تساعد المشرف (اختياري)'),
      '  تفاصيل  '
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'أرسل البلاغ' }));
    expect(await within(dialog).findByRole('status')).toHaveTextContent(
      'وصل بلاغك، وسيراجعه مشرف.'
    );
    expect(await api.bodies('POST', '/reports')).toEqual([
      { target_type: 'post', target_id: POST_ID, reason: 'spam', details: 'تفاصيل' },
    ]);
  });

  it('shows why a report was refused and lets the member try again', async () => {
    member({ 'POST /reports': apiError(429, 'RATE_LIMITED') });
    render(<ReportSheet open onClose={() => {}} targetType="comment" targetId={POST_ID} />);
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'أرسل البلاغ' })).toBeEnabled()
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'أرسل البلاغ' }));
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'أرسل البلاغ' })).toBeEnabled();
  });
});

describe('BlockSheet', () => {
  it('confirms the block and tells the screen, then offers no second block', async () => {
    member({ 'PUT /blocks/other_one': { status: 204 } });
    const onBlocked = vi.fn();
    render(
      <BlockSheet
        open
        onClose={() => {}}
        handle="other_one"
        publicName="[عضو آخر]"
        onBlocked={onBlocked}
      />
    );
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'احجب' })).toBeEnabled());
    await userEvent.click(within(dialog).getByRole('button', { name: 'احجب' }));
    expect(await within(dialog).findByRole('status')).toHaveTextContent('حجبت هذا العضو.');
    expect(onBlocked).toHaveBeenCalledTimes(1);
    expect(within(dialog).queryByRole('button', { name: 'احجب' })).toBeNull();
  });

  it('keeps the sheet open with the failure when the block is refused', async () => {
    member({ 'PUT /blocks/other_one': 'network-error' });
    const onBlocked = vi.fn();
    render(
      <BlockSheet
        open
        onClose={() => {}}
        handle="other_one"
        publicName="[عضو آخر]"
        onBlocked={onBlocked}
      />
    );
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'احجب' })).toBeEnabled());
    await userEvent.click(within(dialog).getByRole('button', { name: 'احجب' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/تعذّر/);
    expect(onBlocked).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'احجب' })).toBeEnabled();
  });
});

describe('WithdrawSheet', () => {
  it('withdraws the post and tells the screen', async () => {
    member({ [`DELETE /posts/${POST_ID}`]: { status: 204 } });
    const onWithdrawn = vi.fn();
    const onClose = vi.fn();
    render(<WithdrawSheet open onClose={onClose} postId={POST_ID} onWithdrawn={onWithdrawn} />);
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'اسحب' }));
    await waitFor(() => expect(onWithdrawn).toHaveBeenCalledTimes(1));
    await userEvent.click(within(dialog).getByRole('button', { name: 'تراجع' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows the failure when the withdrawal is refused', async () => {
    member({ [`DELETE /posts/${POST_ID}`]: apiError(404, 'NOT_FOUND') });
    const onWithdrawn = vi.fn();
    render(<WithdrawSheet open onClose={() => {}} postId={POST_ID} onWithdrawn={onWithdrawn} />);
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'اسحب' }));
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument();
    expect(onWithdrawn).not.toHaveBeenCalled();
  });
});
