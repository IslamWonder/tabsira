'use client';

import { ChoiceGroup } from '@/components/ui/choice-group';
import { SwitchRow } from '@/components/ui/switch-row';
import { messages } from '@/messages';
import {
  CONTRAST,
  LINKS,
  setChoice,
  TEXT_SIZE,
  TEXT_SIZES,
  type TextSize,
  useChoice,
} from '@/preferences/accessibility';
import { SubHeading } from './me-section';

const P = messages.preferences;
const TEXT_SIZE_CHOICES = TEXT_SIZES.map((value) => ({ value, label: P.textSize[value] }));

/**
 * The reading aids of this device (the profile page): a larger text, a
 * stronger contrast and underlined links. Each applies at once, to every
 * page, and is told in words beside its control.
 */
export function ReadingAids() {
  const size = useChoice(TEXT_SIZE);
  const contrast = useChoice(CONTRAST);
  const links = useChoice(LINKS);
  return (
    <>
      <SubHeading>{P.readingAids}</SubHeading>
      <ChoiceGroup<TextSize>
        legend={P.textSize.legend}
        hint={P.textSize.hint}
        options={TEXT_SIZE_CHOICES}
        value={size}
        onChange={(value) => setChoice(TEXT_SIZE, value)}
      />
      <SwitchRow
        label={P.contrast.label}
        hint={P.contrast.hint}
        checked={contrast === 'more'}
        onChange={(on) => setChoice(CONTRAST, on ? 'more' : 'normal')}
      />
      <SwitchRow
        label={P.links.label}
        hint={P.links.hint}
        checked={links === 'underline'}
        onChange={(on) => setChoice(LINKS, on ? 'underline' : 'normal')}
      />
    </>
  );
}
