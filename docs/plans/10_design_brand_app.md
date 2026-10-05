# 10 · Design, logo and app

**Phase:** 1 · **Priority:** High · **Status:** ✅ · **Updated:** 2026-10-05 17:30 (Tunis)

The night and day themes, the AAA game feel, the logo everywhere, phone to desktop, installable as an app.

| Step                                                         | Status | Notes                                                                                                          |
| ------------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------- |
| Logo cleaned and used everywhere, icons and share image      | ✅     | Deep gold by day for contrast.                                                                                 |
| Responsive shell, both themes, motion that respects settings | ✅     |                                                                                                                |
| Large headings in Reem Kufi only, readable text elsewhere    | ✅     |                                                                                                                |
| Accessibility checks clean                                   | ✅     |                                                                                                                |
| Installable app and offline page                             | ✅     | Install offer after a first «تمّ», iPhone steps, «ملفي» › التطبيق, update notice, icon shortcuts (2026-10-05). |
| Landing page from the owners' landing prompt                 | ✅     | Stand-in feature pictures.                                                                                     |

**How we check it**

- Accessibility check at phone, tablet and desktop widths.

## Tasks

### 10.1 Landing page (owners' landing prompt, 5 October 2026)

- **Status:** ✅ 2026-10-05 17:30
- **Goal:** Replace the full-screen rain scene at `/` with a landing page: a deep green hero with a still phone picture and the two ways in («صوّر مشهدًا», «جرّب مثالًا»), the three steps, three feature stories that follow the server's `FEATURE_*` flags, the prepared example with Quran and Sunnah tabs, trust, questions, a closing call and a footer in columns.
- **Touches:** apps/web landing components, home page, top bar (the page's sections for a visitor on `/`), capture sheet («جرّب مثالًا»), footer, tokens.
- **Done when:** 320 to 1440 px without horizontal scroll; the camera only on a tap; features off drop their lines and ways in; related tests pass.
- **Left for the owners:** the three feature pictures of the prompt (`meaning-dialogue.webp`, `world-atlas.webp`, `treasure-community.webp`) were not provided; `apps/web/public/landing/` holds stand-ins cut from the project's own pictures under those names, to be replaced by the real files.
