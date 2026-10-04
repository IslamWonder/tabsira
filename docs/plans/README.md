# Plans

One short file per feature: what it is, where it stands, what is waiting on the owners, and how it is checked. Phase 1 is this release (decision 40); phase 2 follows.

**Updated:** 2026-10-04 17:51 (Tunis) · ✅ done · 🔄 in progress · ⬜ not started · ⏸ phase 2

| #   | Feature                                                           | Phase | Priority | Status |
| --- | ----------------------------------------------------------------- | ----- | -------- | ------ |
| 01  | [Accounts and sign-in](01_accounts.md)                            | 1     | High     | ✅     |
| 02  | [Legal pages, consent and support](02_legal_consent_support.md)   | 1     | High     | ✅     |
| 03  | [Quran and hadith sources](03_scripture_store.md)                 | 1     | Critical | ✅     |
| 04  | [Photo to scan, with honest progress](04_scan_and_progress.md)    | 1     | Critical | 🔄     |
| 05  | [Insight engine](05_insight_engine.md)                            | 1     | Critical | 🔄     |
| 06  | [Insight screen](06_insight_screen.md)                            | 1     | Critical | ✅     |
| 07  | [Personal world](07_personal_world.md)                            | 1     | High     | ✅     |
| 08  | [Practice progress](08_practice_progress.md)                      | 1     | High     | ✅     |
| 09  | [Share card and public insight page](09_share_and_public_page.md) | 1     | High     | ⬜     |
| 10  | [Design, logo and app](10_design_brand_app.md)                    | 1     | High     | ✅     |
| 11  | [Analytics and search engines](11_analytics_seo.md)               | 1     | Medium   | ✅     |
| 12  | [Admin area](12_admin.md)                                         | 1     | Medium   | ✅     |
| 13  | [Scripture, privacy and security reviews](13_reviews.md)          | 1     | Critical | 🔄     |
| 14  | [Deployment and operations](14_deployment.md)                     | 1     | High     | 🔄     |
| 15  | [Quality gates](15_quality.md)                                    | 1     | High     | 🔄     |
| 16  | [Social network «تبصرة تواصل»](16_social_network.md)              | 2     | Medium   | 🔄     |
| 17  | [World atlas «أطلس بصائر العالم»](17_atlas.md)                    | 2     | Medium   | 🔄     |
| 18  | [Camera discovery «اكتشف البصائر حولك»](18_camera_discovery.md)   | 2     | Low      | ⏸      |

## Taking a task

Each feature file ends with numbered tasks. A task is one unit of work for one person or agent on one machine, sized to merge on its own.

1. Pick a task marked ⬜ open whose **Depends on** has merged. Read `AGENTS.md`, `docs/spec/DECISIONS.md` and the feature file first.
2. Claim it: set its status to `🔄 <name>, <machine>`, commit that one line on `main` and push it before you start, so nobody else takes it.
3. Work on a branch named `task/<id>-<short-name>`, touching only what **Touches** lists. If you need another area, say so in the task first.
4. Before merging: rebase onto the latest `main`, re-chain any migration onto the current head, run the gate once (`make lint && make coverage`, under `flock /tmp/tabsira-gate.lock` when several agents share a machine), and get the review the task names.
5. Merge, set the task to ✅ with the date, and update the steps table above it in the same commit.

Two tasks that touch the same files never run at the same time. Waiting on the owners: ask in the task, don't guess.
