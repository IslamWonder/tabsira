import { describe, expect, it } from 'vitest';
import { Busy, createLimiter } from './limiter';

function gate() {
  let open: () => void = () => undefined;
  const wait = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { wait, open };
}

describe('the limit on drawing cards', () => {
  it('runs a task and gives back its answer, and frees the slot when it fails', async () => {
    const limiter = createLimiter(1, 0);
    expect(await limiter.run(async () => 'png')).toBe('png');
    await expect(limiter.run(() => Promise.reject(new Error('x')))).rejects.toThrow('x');
    expect(await limiter.run(async () => 'again')).toBe('again');
  });

  it('runs two at a time, queues the next few and refuses beyond the queue', async () => {
    const limiter = createLimiter(2, 1);
    const started: string[] = [];
    const first = gate();
    const task = (name: string, hold: Promise<void>) => async () => {
      started.push(name);
      await hold;
      return name;
    };
    const a = limiter.run(task('a', first.wait));
    const b = limiter.run(task('b', first.wait));
    const c = limiter.run(task('c', first.wait));
    const d = limiter.run(task('d', first.wait));
    await expect(d).rejects.toBeInstanceOf(Busy);
    await Promise.resolve();
    expect(started).toEqual(['a', 'b']);
    first.open();
    expect(await Promise.all([a, b, c])).toEqual(['a', 'b', 'c']);
    expect(started).toEqual(['a', 'b', 'c']);
    // Everything is free again.
    expect(await limiter.run(async () => 'e')).toBe('e');
  });
});
