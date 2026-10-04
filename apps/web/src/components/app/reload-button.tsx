'use client';

import { Button } from '@/components/ui/button';

/** Tries the page again; used where nothing else can recover (offline). */
export function ReloadButton({ children }: { children: string }) {
  return <Button onClick={() => window.location.reload()}>{children}</Button>;
}
