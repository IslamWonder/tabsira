# 09 · Share card and public insight page

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-04 17:56 (Tunis)

A shareable image of an insight with real Arabic fonts, and a public page for it, with no private data.

| Step                                     | Status | Notes                  |
| ---------------------------------------- | ------ | ---------------------- |
| Publish an insight (server)              | ✅     | Done 2026-10-04 17:51. |
| Share card image                         | ✅     | Done 2026-10-04 17:56. |
| Public insight page with search metadata | ✅     | Done 2026-10-04 17:59. |

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

- **Status:** ✅ done 2026-10-04 17:56
- **Goal:** An image of an insight with real Arabic fonts for sharing, plus the share action.
- **Depends on:** 09.1
- **Touches:** apps/web one image route and the share sheet.
- **Done when:** The image shows the stored text exactly; renders under 1 s.
- **Notes:** `GET /insights/{id}/card.png` (1200×630 PNG drawn by `next/og` from the public payload, kept 5 min in the process and by HTTP caches; the page's `og:image`): title, glimpse, the verse and the hadith **by reference** with the hadith's ruling, one explanation line with its tag, the prepared label, the brand, the disclosure and the link, in IBM Plex Sans Arabic only. The card never draws scripture text: the renderer drops vowel marks and changes letter joining, so it cannot print a stored text byte for byte (scripture review), and the fonts' own character maps gate every string so the renderer never fetches a font from Google. A unit test draws a real card (under 1 s warm, no network). The owner's screen gains «شارك البصيرة»: a sheet that says what becomes public, publishes, then offers the device share sheet, «نسخ الرابط», «تنزيل البطاقة» and «إلغاء النشر». Owners' choices to review: the brief says the image shows the stored text, docs/SEO.md §2 says cards never render scripture; the card follows SEO.md because the renderer cannot be faithful, and a different renderer would be needed otherwise; PNG instead of JPEG (no image library at runtime); no photo until photo storage exists; no rate limit on the card route beyond the caches (an nginx `limit_req` is suggested for production).
