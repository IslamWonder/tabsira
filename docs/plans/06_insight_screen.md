# 06 · Insight screen

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 21:30 (Tunis)

Shows the insight: title, the verse and the hadith with their source and grade, the explanation, «لماذا ظهر هذا؟», a small step, a short chat, and «تمّ».

| Step                                                                   | Status | Notes                                       |
| ---------------------------------------------------------------------- | ------ | ------------------------------------------- |
| Verse and hadith exactly as stored, verse alone while its hadith waits | 🔄     | In progress.                                |
| «لماذا ظهر هذا؟» sheet                                                 | 🔄     |                                             |
| Small step: «من السنة» or «اقتراح عملي»                                | 🔄     |                                             |
| Chat limited to three answers                                          | 🔄     | Needs the chat model chosen in settings.    |
| «تمّ» with the victory moment and world growth                         | 🔄     |                                             |
| Sound effect of the main entity when the insight opens, with a switch  | ✅     | Files uploaded to the bucket by the owners. |

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
