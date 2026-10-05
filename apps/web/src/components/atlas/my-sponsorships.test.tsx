import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { messages } from '@/messages';
import { apiError, mockApi } from '@/test/api';
import { SPONSORSHIP } from '@/test/atlas';
import { MySponsorships } from './my-sponsorships';

const L = messages.atlas.sponsor.list;
describe('MySponsorships', () => {
  it('lists the current sponsorships with a way to each entry, and counts nothing', async () => {
    mockApi({ 'GET /me/sponsorships': { body: [SPONSORSHIP] } });
    render(<MySponsorships />);
    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(within(items[0] as HTMLElement).getByText('[بصيرة تنتظر]')).toBeInTheDocument();
    expect(within(items[0] as HTMLElement).getByText(/بدأت في/)).toBeInTheDocument();
    expect(within(items[0] as HTMLElement).getByRole('link', { name: L.open })).toHaveAttribute(
      'href',
      `/atlas/entries/${SPONSORSHIP.entry_id}`
    );
    expect(screen.queryByText('بصيرتان')).toBeNull();
  });

  it('says when there are none, and when they cannot be read', async () => {
    mockApi({ 'GET /me/sponsorships': { body: [] } });
    const { unmount } = render(<MySponsorships />);
    expect(await screen.findByText(new RegExp(L.empty))).toBeInTheDocument();
    unmount();

    mockApi({ 'GET /me/sponsorships': apiError(503, 'SERVICE_UNAVAILABLE') });
    render(<MySponsorships />);
    expect(await screen.findByRole('alert')).toHaveTextContent(messages.errors.server);
    mockApi({ 'GET /me/sponsorships': { body: [SPONSORSHIP] } });
    await userEvent.click(screen.getByRole('button', { name: messages.atlas.retry }));
    expect(await screen.findByText('[بصيرة تنتظر]')).toBeInTheDocument();
  });

  it('forgets an answer that arrives after the page left', async () => {
    let answer: (() => void) | null = null;
    mockApi({
      'GET /me/sponsorships': () =>
        new Promise((resolve) => {
          answer = () => resolve({ body: [SPONSORSHIP] });
        }),
    });
    const { unmount } = render(<MySponsorships />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    unmount();
    (answer as unknown as () => void)();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText('[بصيرة تنتظر]')).toBeNull();
  });
});
