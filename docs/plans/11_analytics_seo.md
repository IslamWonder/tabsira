# 11 · Analytics and search engines

**Phase:** 1 · **Priority:** Medium · **Status:** 🔄 · **Updated:** 2026-10-04 14:39 (Tunis)

Google Analytics and heatmaps only after consent; pages that search engines and AI crawlers read well.

| Step                                                     | Status | Notes                                                |
| -------------------------------------------------------- | ------ | ---------------------------------------------------- |
| Dynamic sitemap and instant indexing ping on deploy      | ✅     |                                                      |
| Google Analytics after consent, with product events      | ✅     | No personal data in events; paused on account pages. |
| Heatmaps (Microsoft Clarity) after consent               | ✅     | All text masked; to verify with a real project id.   |
| Search metadata, structured data, robots rules, llms.txt | ✅     |                                                      |
| Automatic SEO and site checks in Jenkins                 | ✅     | Accessibility check run by hand for now.             |
| Sitemap served at /sitemap.xml by the web app            | ⬜     | Next.                                                |

**Waiting on the owners**

- Google Analytics id, Clarity project id, Search Console and Bing verification (owners).

**How we check it**

- No request to Google or Clarity before consent (tested).
