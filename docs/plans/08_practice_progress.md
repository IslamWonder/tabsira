# 08 · Practice progress

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-05 (Tunis)

Ranks, streak, daily quest, a sky of meanings and badges. Practice, never a score of faith, and never a comparison with others.

| Step             | Status | Notes                       |
| ---------------- | ------ | --------------------------- |
| Rules and data   | ✅     | Built; merges after review. |
| «تمرينك» screens | 🔄     | Sky of meanings redesign.   |

**How we check it**

- Wording checked against the learning-path rules.

## Tasks

### 08.1 Practice progress screens

- **Status:** ✅ 2026-10-04 16:09
- **Goal:** Ranks, streak, quest, sky, badges.
- **Depends on:** 04.1
- **Touches:** apps/web progress components, «ملفي».
- **Done when:** Wording follows the learning-path rules.

### 08.2 Sky of meanings, the cinematic scene

- **Status:** 🔄 2026-10-05 — each star carries the insights that taught it (`StarOut.insights`).
- **Goal:** The owners' reference: a full-width night scene over the emerald nebula picture, real star buttons with their names, one pearl dock for the chosen meaning that opens its insights.
- **Depends on:** 08.1
- **Touches:** `GET /me/progress` (additive field), apps/web progress components, `apps/web/public/practice/`.
- **Done when:** The scene matches the reference at 1536×1024 and 390 px, every state (loading, empty, error, updating) is drawn, and the dock opens the star's own insights.
