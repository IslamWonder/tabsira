/*
 * The one global answer of the API that is not an error for the screen that
 * met it: 403 LEGAL_ACCEPTANCE_REQUIRED (owner decision 35). The signed-in
 * account has not accepted the current terms and privacy policy; every API
 * client reports it here, and the session opens the acceptance gate.
 */

const listeners = new Set<() => void>();

export function onLegalRequired(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function signalLegalRequired(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** Whether a response is that refusal; it reads a copy of the body, so the caller still can. */
export async function isLegalRefusal(response: Response): Promise<boolean> {
  if (response.status !== 403) {
    return false;
  }
  try {
    const body = (await response.clone().json()) as { error?: unknown };
    return (
      typeof body.error === 'string' && body.error.toUpperCase() === 'LEGAL_ACCEPTANCE_REQUIRED'
    );
  } catch {
    return false;
  }
}
