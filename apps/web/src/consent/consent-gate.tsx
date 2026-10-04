'use client';

import type { ReactNode } from 'react';
import type { OptionalCategory } from './contract';
import { isGranted, useConsent } from './store';

/**
 * Renders its children only once the visitor's recorded choice allows
 * `category`. The analytics tools are placed inside one of these, so no tag
 * is ever injected before consent (owner decisions 28, 31 and 32).
 */
export function ConsentGate({
  category,
  children,
}: {
  category: OptionalCategory;
  children: ReactNode;
}) {
  const { consent } = useConsent();
  return isGranted(consent, category) ? children : null;
}
