import type { Route as NextRoute } from 'next';
import { beforeEach, describe, expect, it } from 'vitest';
import { forgetHandedPhoto, handedPhoto, handPhoto } from './photo-handoff';

const PHOTO = { src: '/p', width: 4, height: 3, backHref: '/scan/1' as NextRoute };

beforeEach(forgetHandedPhoto);

describe('photo handoff', () => {
  it('gives the photo to the one insight it was handed to, and the last hand wins', () => {
    expect(handedPhoto('a')).toBeNull();
    handPhoto('a', PHOTO);
    expect(handedPhoto('a')).toBe(PHOTO);
    expect(handedPhoto('b')).toBeNull();
    handPhoto('b', PHOTO);
    expect(handedPhoto('a')).toBeNull();
  });
});
