'use client';

import { useSyncExternalStore } from 'react';
import {
  type InstallState,
  installSnapshot,
  serverInstallSnapshot,
  subscribeInstall,
} from './install';

/** The install state of this browser, kept current by the browser's own events. */
export function useInstall(): InstallState {
  return useSyncExternalStore(subscribeInstall, installSnapshot, serverInstallSnapshot);
}

/** Fired on the window when a first insight is done: the moment the app may be offered. */
export const ENGAGED_EVENT = 'tabsira:engaged';
