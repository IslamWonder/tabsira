import type { Metadata } from 'next';
import { SceneExperience } from '@/components/scene/scene-experience';

export const metadata: Metadata = {
  alternates: { canonical: '/' },
};

/** The scene: the prepared rain photo first, before any account or permission (tajriba A01). */
export default function ScenePage() {
  return <SceneExperience />;
}
