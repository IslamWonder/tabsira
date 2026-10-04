/**
 * Accepts a pasted image address the way people paste it (Postel's law):
 * surrounding spaces, no scheme, a protocol-relative form. Returns the
 * absolute http(s) address, or null when it is not one.
 */
export function normaliseImageLink(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === '' || /\s/.test(trimmed)) {
    return null;
  }
  const withScheme = trimmed.startsWith('//')
    ? `https:${trimmed}`
    : /^[a-z][a-z0-9+.-]*:/i.test(trimmed)
      ? trimmed
      : `https://${trimmed}`;
  try {
    const url = new URL(withScheme);
    return (url.protocol === 'https:' || url.protocol === 'http:') && url.hostname.includes('.')
      ? url.href
      : null;
  } catch {
    return null;
  }
}

/** Only images go to the analysis; anything else gets a clear message, not a silent failure. */
export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/');
}
