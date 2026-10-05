// Next's own route matcher, used by a test to read `headers()` sources the way Next does.
declare module 'next/dist/compiled/path-to-regexp' {
  export function pathToRegexp(path: string, keys?: unknown[], options?: object): RegExp;
}
