import { describe, expect, it } from 'vitest';
import { formText } from './form-text';

describe('formText', () => {
  it('reads a text field as it was typed', () => {
    const form = new FormData();
    form.set('email', ' a@b.tn ');
    expect(formText(form, 'email')).toBe(' a@b.tn ');
  });

  it('reads a missing field or a file as the fallback, never as "null"', () => {
    const form = new FormData();
    form.set('photo', new File(['x'], 'x.png'));
    expect(formText(form, 'email')).toBe('');
    expect(formText(form, 'photo')).toBe('');
    expect(formText(form, 'return', '/')).toBe('/');
  });
});
