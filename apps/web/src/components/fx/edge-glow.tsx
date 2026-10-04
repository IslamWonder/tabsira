/**
 * A light breathing at the edges of the screen while something is working
 * (the status vignette of a game HUD). Fixed, transparent to the pointer,
 * below sheets and dialogs; still under reduced motion.
 */
export function EdgeGlow({ active }: { active: boolean }) {
  if (!active) {
    return null;
  }
  return (
    <div
      aria-hidden="true"
      data-edge-glow="active"
      className="pointer-events-none fixed inset-0 z-30 animate-[fx-breathe-edge_2.6s_ease-in-out_infinite]"
      style={{ boxShadow: 'inset 0 0 140px var(--edge-glow)' }}
    />
  );
}
