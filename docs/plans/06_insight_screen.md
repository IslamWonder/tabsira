# 06 · Insight screen

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-05 11:10 (Tunis)

Shows the insight: title, the verse and the hadith with their source and grade, the explanation, «لماذا ظهر هذا؟», a small step, a short chat, and «تمّ».

| Step                                                                   | Status | Notes                                       |
| ---------------------------------------------------------------------- | ------ | ------------------------------------------- |
| Verse and hadith exactly as stored, verse alone while its hadith waits | 🔄     | In progress.                                |
| «لماذا ظهر هذا؟» sheet                                                 | 🔄     |                                             |
| Small step: «من السنة» or «اقتراح عملي»                                | 🔄     |                                             |
| Chat limited to three answers                                          | 🔄     | Needs the chat model chosen in settings.    |
| «تمّ» with the victory moment and world growth                         | 🔄     |                                             |
| Sound effect of the main entity when the insight opens, with a switch  | ✅     | Files uploaded to the bucket by the owners. |
| Scene sound looping around the photo while the insight is prepared     | ✅     | Silent before any verse shows.              |

**How we check it**

- Accessibility check; related tests.

## Tasks

### 06.1 Insight screen

- **Status:** ✅ 2026-10-04 16:09
- **Goal:** Verse, hadith, explanation, «لماذا ظهر هذا؟», small step, chat, «تمّ».
- **Depends on:** 04.1
- **Touches:** apps/web insight components and route.
- **Done when:** Accessibility check; scripture text untouched (source guards).

### 06.2 Sound effect of an opened insight

- **Status:** ✅ 2026-10-04 21:30
- **Goal:** One short sound per ontology entity plays when an insight opens; the reader can switch it off from the top bar, the insight page and the profile page.
- **Depends on:** 06.1
- **Touches:** `apps/api/src/routers/sounds.py`, `apps/api/src/storage/sounds.py`, `apps/web/src/lib/sound`, `apps/web/src/preferences/sound.ts`, the sound switch components.
- **Done when:** `GET /sounds/ontology/<id>` serves `static/ontology/audio/<id>.mp3` of the bucket; related tests. The switch is per device; the account does not keep it.
- **Superseded by 06.3:** the insight page no longer plays a sound; the scene's sound is heard during the scan.

### 06.3 Scene sound while the insight is prepared

- **Status:** ✅ 2026-10-05 11:10
- **Goal:** The sound is known as soon as the scene is matched to the ontology, so it is heard while the AI works, not after. The owners' rule: no sound around the verse, only around the photo while it is processed.
- **Depends on:** 06.2
- **Touches:** `apps/api/src/scans/sound.py`, `apps/api/src/scans/workflow.py` (a `sound` event on the scan stream right after «أفهم المشهد»), `apps/web/src/lib/sound/player.ts` (`loopSound`, `endLoop`), `apps/web/src/components/scan/use-scene-sound.ts`, the speaker in the scan photo's corner.
- **Rules:** the first resolved entity of the scene (or of the chosen focus) with an uploaded sound, at most three tried; none for a sensitive scene or an entity the ontology blocks or wants clarified. The sound loops; when the run ends it finishes the loop it plays, or one more when under two seconds of it are left, fading out before its end; a failure fades it out at once; opening an insight fades it out, so it never plays with a verse. The speaker silences it in one tap; its ring breathes while the sound loops, and is still under reduced motion.
- **Done when:** related tests in `tests/insight/test_scene_sound.py`, `tests/scans/test_workflow.py`, the player, the hook and the scan screen.
