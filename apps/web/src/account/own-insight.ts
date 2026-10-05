/**
 * Whether the account last seen on this device holds an insight of its own
 * (decision 64: its home is the capture, not the welcome). Kept on the device
 * so the first paint, before the session is known, shows the right opening:
 * the inline head script marks <html data-own-insight> from it, and CSS hides
 * the other opening (globals.css). The session sets and clears it; the API's
 * answer always wins once it arrives. No module dependency: the head script
 * and the layout read the key on the server too.
 */
export const OWN_INSIGHT_KEY = 'tabsira.own-insight';
export const OWN_INSIGHT_ATTRIBUTE = 'data-own-insight';

/** Remember what the session says now; a blocked storage only loses the head start. */
export function rememberOwnInsight(held: boolean): void {
  try {
    if (held) {
      window.localStorage.setItem(OWN_INSIGHT_KEY, '1');
    } else {
      window.localStorage.removeItem(OWN_INSIGHT_KEY);
    }
  } catch {
    // Private mode or blocked storage: the welcome may show for a moment, as before.
  }
}
