import { OWN_INSIGHT_ATTRIBUTE, OWN_INSIGHT_KEY } from '@/account/own-insight';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { READING_AIDS } from './accessibility';
import { MOTION_STORAGE_KEY } from './motion';

/** Sets a stored reading aid's attribute, only for one of its known values other than the default. */
const readingAids = READING_AIDS.map((aid) => {
  const values = aid.values.filter((value) => value !== aid.fallback);
  return (
    `var a=s.getItem(${JSON.stringify(aid.key)});` +
    `if(${JSON.stringify(values)}.indexOf(a)>-1){d.setAttribute(${JSON.stringify(`data-${aid.attribute}`)},a)}`
  );
}).join('');

/**
 * Runs inline in <head>, before the first paint, so a stored theme, motion
 * or reading-aid choice never flashes the other one, nor the home page's other opening. Plain ES5 on purpose: it is not
 * transpiled. A blocked storage leaves the device in charge.
 */
export const PREFERENCES_INIT_SCRIPT = [
  'try{var d=document.documentElement,s=window.localStorage;',
  `var t=s.getItem(${JSON.stringify(THEME_STORAGE_KEY)});`,
  'if(t==="light"||t==="dark"){d.setAttribute("data-theme",t)}',
  `if(s.getItem(${JSON.stringify(MOTION_STORAGE_KEY)})==="off"){d.setAttribute("data-motion","reduce")}`,
  readingAids,
  // The home page's opening, before the session is known (src/account/own-insight.ts).
  `if(s.getItem(${JSON.stringify(OWN_INSIGHT_KEY)})==="1"){d.setAttribute(${JSON.stringify(OWN_INSIGHT_ATTRIBUTE)},"")}`,
  '}catch(e){}',
].join('');
