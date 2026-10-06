/** A text field of a submitted form; a missing field or a file reads as `fallback`. */
export function formText(form: FormData, name: string, fallback = ''): string {
  const value = form.get(name);
  return typeof value === 'string' ? value : fallback;
}
