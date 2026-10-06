// @vitest-environment node
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { useSoundPlaying } from '@/lib/sound/player';
import { TEXT_SIZE, useChoice } from './accessibility';

function Probe() {
  return <p>{`${useChoice(TEXT_SIZE)} ${useSoundPlaying()}`}</p>;
}

describe('the reading aids and the sound on the server', () => {
  it('render the defaults: the device applies its own choice before the first paint', () => {
    expect(renderToString(<Probe />)).toContain('normal false');
  });
});
