/**
 * The white flash of a shutter over its `relative` parent. Each new `trigger`
 * value plays it once (a new key remounts the span); zero shows nothing.
 */
export function Flash({ trigger }: Readonly<{ trigger: number }>) {
  if (trigger === 0) {
    return null;
  }
  return (
    <span
      key={trigger}
      aria-hidden="true"
      data-flash={trigger}
      className="pointer-events-none absolute inset-0 rounded-[inherit] bg-[var(--point-gold-core)] opacity-0 animate-[fx-flash_0.55s_ease-out]"
    />
  );
}
