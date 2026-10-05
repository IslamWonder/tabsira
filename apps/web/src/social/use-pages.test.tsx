import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Failure, Result } from '@/lib/api/result';
import { type Page, usePages } from './use-pages';

type Answer = Result<Page<string, string>>;

const page = (
  items: string[],
  next: string | null = null,
  reason: string | null = null
): Answer => ({
  ok: true,
  status: 200,
  data: { items, next_cursor: next, empty_reason: reason },
});

const NETWORK: Failure = { ok: false, code: 'NETWORK', status: 0, fields: [], retryAfter: null };

describe('usePages', () => {
  it('loads the first page on display and the next one on request', async () => {
    const fetchPage = vi.fn(async (cursor: string | null) =>
      cursor === null ? page(['a'], 'c1') : page(['b'])
    );
    const { result } = renderHook(() => usePages(fetchPage, 'list'));
    expect(result.current.status).toEqual({ kind: 'loading' });
    await waitFor(() => expect(result.current.status).toMatchObject({ kind: 'ready', more: true }));
    act(() => result.current.loadMore());
    expect(result.current.status).toEqual({ kind: 'loading-more' });
    await waitFor(() => expect(result.current.items).toEqual(['a', 'b']));
    expect(result.current.status).toEqual({ kind: 'ready', emptyReason: null, more: false });
    expect(fetchPage).toHaveBeenLastCalledWith('c1');
  });

  it('reports a failure, reloads, and keeps the empty reason of the first page', async () => {
    const fetchPage = vi
      .fn<(cursor: string | null) => Promise<Answer>>()
      .mockResolvedValueOnce(NETWORK)
      .mockResolvedValueOnce(page([], null, 'nothing_yet'));
    const { result } = renderHook(() => usePages(fetchPage, 'list'));
    await waitFor(() => expect(result.current.status.kind).toBe('failed'));
    act(() => result.current.reload());
    await waitFor(() =>
      expect(result.current.status).toEqual({
        kind: 'ready',
        emptyReason: 'nothing_yet',
        more: false,
      })
    );
  });

  it('drops a late answer for a list that was replaced', async () => {
    const answers = new Map<string, (answer: Answer) => void>();
    const fetchPage = vi.fn(
      (_cursor: string | null) =>
        new Promise<Answer>((resolve) => {
          answers.set(String(answers.size), resolve);
        })
    );
    const { result, rerender } = renderHook(({ key }) => usePages(fetchPage, key), {
      initialProps: { key: 'first' },
    });
    rerender({ key: 'second' });
    await waitFor(() => expect(answers.size).toBe(2));
    await act(async () => {
      answers.get('0')?.(page(['old']));
    });
    expect(result.current.items).toEqual([]);
    await act(async () => {
      answers.get('1')?.(page(['new']));
    });
    expect(result.current.items).toEqual(['new']);
  });

  it('asks nothing while disabled, then starts over once enabled', async () => {
    const fetchPage = vi.fn(async () => page(['a']));
    const { result, rerender } = renderHook(({ enabled }) => usePages(fetchPage, 'list', enabled), {
      initialProps: { enabled: false },
    });
    expect(fetchPage).not.toHaveBeenCalled();
    expect(result.current.status).toEqual({ kind: 'loading' });
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.items).toEqual(['a']));
  });

  it('replaces, removes, prepends and appends items in place', async () => {
    const fetchPage = vi.fn(async () => page(['a', 'b']));
    const { result } = renderHook(() => usePages(fetchPage, 'list'));
    await waitFor(() => expect(result.current.items).toEqual(['a', 'b']));
    act(() => result.current.replace((item) => item === 'a', 'A'));
    expect(result.current.items).toEqual(['A', 'b']);
    act(() => result.current.replace((item) => item === 'b', null));
    expect(result.current.items).toEqual(['A']);
    act(() => result.current.prepend('first'));
    act(() => result.current.append('last'));
    expect(result.current.items).toEqual(['first', 'A', 'last']);
  });

  it('replaces from the item the list holds now, not from an earlier render', async () => {
    const fetchPage = vi.fn(async () => page(['a', 'b']));
    const { result } = renderHook(() => usePages(fetchPage, 'list'));
    await waitFor(() => expect(result.current.items).toEqual(['a', 'b']));
    act(() => result.current.replace((item) => item === 'a', null));
    expect(result.current.items).toEqual(['b']);
    // An updater captured before the removal still works on what is in the list.
    act(() =>
      result.current.replace(
        (item) => item === 'b',
        (current) => `${current}!`
      )
    );
    expect(result.current.items).toEqual(['b!']);
    act(() =>
      result.current.replace(
        (item) => item === 'b!',
        () => null
      )
    );
    expect(result.current.items).toEqual([]);
  });
});
