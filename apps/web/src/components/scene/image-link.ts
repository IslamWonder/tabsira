/**
 * Accepts a pasted image address the way people paste it (Postel's law):
 * surrounding spaces, no scheme, a protocol-relative form. Returns the
 * absolute http(s) address, or null when it is not one.
 */
/** Only images go to the analysis; anything else gets a clear message, not a silent failure. */
export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/');
}
