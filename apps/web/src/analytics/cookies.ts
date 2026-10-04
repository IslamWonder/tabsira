/**
 * Deletes the cookies an analytics tool set, when the visitor withdraws. A
 * tool writes them on the site's registrable domain, so every parent domain of
 * the host is tried as well as the host itself.
 */
export function domainsOf(hostname: string): string[] {
  const labels = hostname.split('.');
  const isAddress = /^[\d.]+$/.test(hostname);
  const parents = isAddress
    ? []
    : labels.slice(0, -1).map((_, index) => `; Domain=.${labels.slice(index).join('.')}`);
  return ['', ...parents];
}

export function expireCookies(names: RegExp): void {
  const found = document.cookie
    .split(';')
    .map((part) => part.trim().replace(/=.*/s, ''))
    .filter((name) => names.test(name));
  for (const name of found) {
    for (const domain of domainsOf(window.location.hostname)) {
      // biome-ignore lint/suspicious/noDocumentCookie: expiring the cookies of a tool the visitor withdrew from.
      document.cookie = `${name}=; Path=/${domain}; Max-Age=0`;
    }
  }
}
