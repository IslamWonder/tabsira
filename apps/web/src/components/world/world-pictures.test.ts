import { describe, expect, it, vi } from 'vitest';
import { loadPicture } from './world-pictures';

/** An image that loads, or fails, as soon as it is given an address. */
function stubImage(loads: boolean) {
  vi.stubGlobal(
    'Image',
    class {
      decoding = '';
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => (loads ? this.onload?.() : this.onerror?.()));
      }
    }
  );
}

describe('loadPicture', () => {
  it('gives the picture once it is loaded, and null when it fails', async () => {
    stubImage(true);
    expect(await loadPicture('/world/clouds-1.webp')).not.toBeNull();
    stubImage(false);
    expect(await loadPicture('/world/clouds-1.webp')).toBeNull();
  });
});
