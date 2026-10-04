# 09 · Share card and public insight page

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 17:04 (Tunis)

A shareable image of an insight with real Arabic fonts, and a public page for it, with no private data.

| Step                                     | Status | Notes                           |
| ---------------------------------------- | ------ | ------------------------------- |
| Share card image                         | ⬜     | Next, after the insight screen. |
| Public insight page with search metadata | ✅     | API 09.1, page 09.2.            |

**How we check it**

- Card renders the stored text exactly; privacy review.

## Tasks

### 09.1 Publish an insight publicly (server)

- **Status:** ✅ 2026-10-04 16:56
- **Goal:** The owner publishes or withdraws one insight; a public read route returns only published insights, by public id, with no private data and photos only under the consent rules.
- **Depends on:** 04.1
- **Touches:** apps/api insights (one route group, one migration), docs/PRIVACY.md.
- **Done when:** Unpublished or withdrawn returns 404; privacy review; 100 % coverage.
- **Notes:** Public path `/i/{id}`, API `GET /public/insights/{id}` (cached 5 min), `POST`/`DELETE /insights/{id}/publish`; verified accounts only, never under 13, never a simulation or a personalised insight; the insights sitemap section lists them. Owners' choices to review: 404 (not SEO.md's 410) for a withdrawn insight; no photo until photo storage exists; no moderation hold or report target for public insights yet; no server-side preview (the owner's own view is the preview).

### 09.2 Public insight page

- **Status:** ✅ 2026-10-04 17:04
- **Goal:** A public page for a published insight, with the verse and hadith exactly as stored, search metadata and structured data from `apps/web/src/lib/seo.ts`.
- **Depends on:** 09.1, 06.1
- **Touches:** apps/web one public route and its components.
- **Done when:** check:seo passes; scripture text untouched.
- **Notes:** Route `apps/web/src/app/i/[id]`, server-rendered from `GET /public/insights/{id}` with `generateMetadata` (article type, canonical `/i/{id}`), WebPage, BreadcrumbList and Article JSON-LD (author: the public name or the site). Reuses the evidence cards and explanation sections; the step is read-only; no photo, no chat, no buttons. `check:seo` walks only the listed static routes, so the page is checked by its unit tests (metadata lengths, canonical, hash of the printed scripture).

### 09.3 Share card image

- **Status:** ⬜ open
- **Goal:** An image of an insight with real Arabic fonts for sharing, plus the share action.
- **Depends on:** 09.1
- **Touches:** apps/web one image route and the share sheet.
- **Done when:** The image shows the stored text exactly; renders under 1 s.
