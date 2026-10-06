/*
 * The launch of the installed app on a phone (DESIGN_DECISION.md «Launch
 * splash»): the system splash shows the icon on the night ground, then the web
 * page takes over with the logo written in full screen. Decided before the first
 * paint, so the page never flashes under it.
 */

/** Set on <html> while the splash plays; the splash is hidden without it. */
export const LAUNCH_ATTRIBUTE = 'data-launch';
/** Once a launch: a reload or a navigation in the same window does not play it again. */
export const LAUNCH_KEY = 'tabsira:launched';
/** The splash's length before it fades (launch.css), and the fade. */
export const LAUNCH_MS = 2900;
export const LAUNCH_FADE_MS = 500;

/**
 * Runs inline in <head>, after the preference script (which may set
 * data-motion). Only the installed app (standalone, or iOS's home screen), only
 * below the tablet width, never with reduced motion, once a window. Plain ES5:
 * it is not transpiled. A blocked storage plays nothing.
 */
export const LAUNCH_SCRIPT = [
  'try{var d=document.documentElement,m=window.matchMedia,s=window.sessionStorage;',
  'var installed=m("(display-mode: standalone)").matches||window.navigator.standalone===true;',
  'if(installed&&m("(max-width: 767.98px)").matches&&!m("(prefers-reduced-motion: reduce)").matches',
  `&&d.getAttribute("data-motion")!=="reduce"&&!s.getItem(${JSON.stringify(LAUNCH_KEY)})){`,
  `s.setItem(${JSON.stringify(LAUNCH_KEY)},"1");d.setAttribute(${JSON.stringify(LAUNCH_ATTRIBUTE)},"")}`,
  '}catch(e){}',
].join('');
