# 09 · Share card and public insight page

**Phase:** 1 · **Priority:** High · **Status:** ⬜ · **Updated:** 2026-10-04 17:59 (Tunis)

A shareable image of an insight with real Arabic fonts, and a public page for it, with no private data.

| Step                                     | Status | Notes                           |
| ---------------------------------------- | ------ | ------------------------------- |
| Publish an insight (server)              | ✅     | Done 2026-10-04 17:51.          |
| Share card image                         | ⬜     | Next, after the insight screen. |
| Public insight page with search metadata | ✅     | Done 2026-10-04 17:59.          |

**How we check it**

- Card renders the stored text exactly; privacy review.

## Tasks

### 09.1 Publish an insight publicly (server)

- **Status:** ✅ done 2026-10-04 17:51
- **Goal:** The owner publishes or withdraws one insight; a public read route returns only published insights, by public id, with no private data and photos only under the consent rules.
- **Depends on:** 04.1
- **Touches:** apps/api insights (one route group, one migration), docs/PRIVACY.md.
- **Done when:** Unpublished or withdrawn returns 404; privacy review; 100 % coverage.

### 09.2 Public insight page

- **Status:** ✅ done 2026-10-04 17:59
- **Goal:** A public page for a published insight, with the verse and hadith exactly as stored, search metadata and structured data from `apps/web/src/lib/seo.ts`.
- **Depends on:** 09.1, 06.1
- **Touches:** apps/web one public route and its components.
- **Done when:** check:seo passes; scripture text untouched.

### 09.3 Share card image

- **Status:** ⬜ open
- **Goal:** An image of an insight with real Arabic fonts for sharing, plus the share action.
- **Depends on:** 09.1
- **Touches:** apps/web one image route and the share sheet.
- **Done when:** The image shows the stored text exactly; renders under 1 s.
