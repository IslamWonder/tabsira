import { burstFrom } from './burst';

export const VICTORY_EVENT = 'tabsira:victory';

/**
 * The end of the journey (Peak-End rule): a burst of light from the element
 * and the banner "meaning discovered". Call it after the save has succeeded,
 * never on the tap alone.
 */
export function celebrate(element: Element): void {
  burstFrom(element);
  window.dispatchEvent(new Event(VICTORY_EVENT));
}
