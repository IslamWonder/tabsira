'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api/client';
import { attempt } from '@/lib/api/result';

/**
 * Whether Google sign-in can be offered: `GET /auth/providers` says so, and
 * the button is shown only then (an unconfigured Google answers 503, so a
 * button that cannot work is never shown). `null` while the API has not
 * answered; a failure counts as unavailable.
 */
let cached: Promise<boolean> | null = null;

export function loadGoogleAvailable(): Promise<boolean> {
  cached ??= attempt(api.GET('/auth/providers')).then((result) => {
    if (!result.ok) {
      cached = null;
      return false;
    }
    return result.data.providers.some((provider) => provider.id === 'google' && provider.available);
  });
  return cached;
}

/** Forgets the answer, as at a fresh page load (between unit tests). */
export function forgetProviders(): void {
  cached = null;
}

export function useGoogleAvailable(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    void loadGoogleAvailable().then((value) => {
      if (live) {
        setAvailable(value);
      }
    });
    return () => {
      live = false;
    };
  }, []);
  return available;
}
