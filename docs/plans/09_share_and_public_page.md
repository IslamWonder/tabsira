# 09 · Share card and public insight page

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 20:45 (Tunis)

A shareable image of an insight with real Arabic fonts, and a public page for it, with no private data.

| Step                                     | Status | Notes                           |
| ---------------------------------------- | ------ | ------------------------------- |
| Publish an insight (server)              | ✅     | Done 2026-10-04 17:51.          |
| Share card image                         | ✅     | Done 2026-10-04 18:26. Card OK. |
| Public insight page with search metadata | ✅     | Done 2026-10-04 17:59.          |
| Share download, card size, inspector     | ✅     | Done 2026-10-04 20:45.          |

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

- **Status:** ✅ done 2026-10-04 18:26
- **Goal:** An image of an insight with real Arabic fonts for sharing, plus the share action.
- **Depends on:** 09.1
- **Touches:** apps/web one image route and the share sheet.
- **Done when:** The image shows the stored text exactly; renders under 1 s.
- **Notes:** outside the Touches list, the card route is metered in `nginx/production/tabsira.me.conf` (and mirrored in `nginx/local/tabsira.test.conf`): its own `limit_req` zone, 2 requests a second with a burst of 10, the security headers included in that location; the privacy text (`docs/PRIVACY.md`, the privacy and terms pages) was updated for the card in the same task.

### 09.4 Share download, card size and the developer panel

- **Status:** ✅ done 2026-10-04 20:45
- **Goal:** Close three gaps of the wave 5 compliance audit: the share sheet offers «تنزيل» of the card image (v2 §18); the card is tested to stay under 300 KB (v2 §25) and is encoded as a palette PNG to stay there; the developer panel `/dev/inspect/{scanId}` of v2 §23 exists, behind an admin session.
- **Depends on:** 09.3, 12.1
- **Touches:** apps/web share sheet, share-card compose and its tests, `app/dev/inspect/[scanId]` (development only), `config/server-env.ts`; apps/api `admin/views/inspector.py` and its template, `FEATURE_DEV_INSPECTOR` in config and both environment templates; docs/ADMIN.md.
- **Done when:** The download link appears for a public insight only; every card fixture, the longest verse included, is under 300 KB; the inspector shows status, stages with times, model names and costs, entities and the insights' references, never the photo or the person; it is audited, gone when the flag is off, and the web route redirects to it.
- **Notes:** The web `/dev/inspect/{scanId}` redirects to `ADMIN_URL/admin/inspect/{scanId}` rather than rendering, because the admin session cookie lives on the admin host alone (`Path=/admin`, no `Domain`); the panel is a sqladmin view so the host check, the second factor, CSRF and the audit log apply unchanged. Production sets `FEATURE_DEV_INSPECTOR=false` (v2 §23: off in production).

### 09.5 A link preview with the published photo

- **Status:** ✅ 2026-10-05, owners' decision (amends decision 53 for photos the owner already made public).
- **What:** `/insights/{id}/preview` draws the 1200 x 630 picture that WhatsApp, Facebook, X and Telegram show for a published insight: the photo's public copy when the owner already published it (a public post or map entry made it; the API gives it as `photo_url`), else the night ground, with the title, the glimpse, the mark and the site's name, never the verse or the hadith. The page's `og:image` and `twitter:image` point to it; the title and the glimpse are the preview's text. Drawn by Pango through sharp (`src/lib/share-card/preview.ts`), never kept by a cache.
- **Extended:** 2026-10-06, owners' request. A public post (`/posts/{id}/preview`) and a published map entry (`/atlas/entries/{id}/preview`) get the same picture instead of the site's generic card, read as a stranger reads them; a post shown to followers only or not published has none. No API or data-flow change: the photo is the public copy the page already shows.

### 09.6 One-tap sharing

- **Status:** ✅ 2026-10-06, owners' request. The completion panel's «شارك» button (with the share icon) and the insight footer's share button publish when needed and open the system share dialog in the same tap (the call is made before the publication is awaited, which iOS requires); desktop copies the link; «خيارات النشر» opens the sheet. No API or data-flow change.
- **Fix:** 2026-10-06. «خيارات النشر» also sits under the footer's share button whenever the insight can be shared and the completion panel is not on screen, so an insight finished and published on an earlier visit can still be withdrawn (the privacy text promises it stops showing once withdrawn).
