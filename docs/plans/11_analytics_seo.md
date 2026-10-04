# 11 · Analytics and search engines

**Phase:** 1 · **Priority:** Medium · **Status:** ✅ · **Updated:** 2026-10-04 15:20 (Tunis)

Google Analytics and heatmaps only after consent; pages that search engines and AI crawlers read well.

| Step                                                     | Status | Notes                                                |
| -------------------------------------------------------- | ------ | ---------------------------------------------------- |
| Dynamic sitemap and instant indexing ping on deploy      | ✅     |                                                      |
| Google Analytics after consent, with product events      | ✅     | No personal data in events; paused on account pages. |
| Heatmaps (Microsoft Clarity) after consent               | ✅     | All text masked; to verify with a real project id.   |
| Search metadata, structured data, robots rules, llms.txt | ✅     |                                                      |
| Automatic SEO and site checks in Jenkins                 | ✅     | Accessibility check in its own stage (RUN_A11Y).     |
| Sitemap served at /sitemap.xml by the web app            | ✅     | Index and children from the API; 503 if it is down.  |

**Waiting on the owners**

- Google Analytics id, Clarity project id, Search Console and Bing verification (owners).

**How we check it**

- No request to Google or Clarity before consent (tested).

## Tasks

### 11.1 Serve /sitemap.xml from the web app

- **Status:** ✅ 2026-10-04 15:16
- **Goal:** The web app serves the sitemap index and sections from the API; the static list drops pages that do not exist (/about, /cookies) or they get pages.
- **Depends on:** —
- **Touches:** apps/web sitemap route, apps/api sitemap static list.
- **Done when:** robots.txt and the sitemap agree; check:site passes.

### 11.2 Accessibility check in CI

- **Status:** ✅ 2026-10-04 15:19
- **Goal:** Run check:a11y in Jenkins with Chromium and sample API answers.
- **Depends on:** —
- **Touches:** Jenkinsfile, jenkins/web-a11y.sh, jenkins/jenkins.env, apps/web scripts, docs/JENKINS_SETUP.md.
- **Done when:** The Jenkins stage fails on any violation.
