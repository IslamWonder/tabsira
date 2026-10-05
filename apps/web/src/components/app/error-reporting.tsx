'use client';

import { useEffect } from 'react';
import { installErrorReporting } from '@/lib/errors/report';

/**
 * Starts sending the browser's uncaught errors to the API, in production
 * builds only: in development the console and the overlay already show them.
 */
export function ErrorReporting({
  enabled = process.env.NODE_ENV === 'production',
}: {
  enabled?: boolean;
}) {
  useEffect(() => {
    if (enabled) {
      installErrorReporting();
    }
  }, [enabled]);
  return null;
}
