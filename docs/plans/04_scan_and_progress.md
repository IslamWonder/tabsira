# 04 · Photo to scan, with honest progress

**Phase:** 1 · **Priority:** Critical · **Status:** 🔄 · **Updated:** 2026-10-04 14:51 (Tunis)

A person takes or uploads a photo. They see honest stages (understanding, searching, verifying, composing), can point at what matters and answer one question.

| Step                                                                    | Status | Notes                       |
| ----------------------------------------------------------------------- | ------ | --------------------------- |
| Upload or link, size and safety checks                                  | ✅     | Built; merges after review. |
| Queue with one worker, progress that resumes after a drop               | ✅     | Built; merges after review. |
| Photo shown only after the safety verdict; sensitive scenes never shown | ✅     |                             |
| Focus and one clarifying question                                       | ✅     |                             |
| Rain tutorial, labelled as prepared                                     | ✅     |                             |
| Scripture review fixes, then merge                                      | 🔄     | In progress.                |
| Screens: capture, progress, focus, question                             | 🔄     | In progress.                |

**How we check it**

- A live run end to end on `https://tabsira.test`.
- Scripture and privacy reviews passed.

## Tasks

### 04.1 Scan workflow: scripture fixes and merge

- **Status:** 🔄 main machine
- **Goal:** Close the scripture review findings, then merge.
- **Depends on:** —
- **Touches:** apps/api scans, insights, world, me, tutorial.
- **Done when:** Scripture review passes; gate green.

### 04.2 Scan screens: capture, progress, focus, question

- **Status:** 🔄 main machine
- **Goal:** Web screens for 04, built on the workflow API.
- **Depends on:** 04.1
- **Touches:** apps/web scan and insight components.
- **Done when:** Screenshots phone and desktop, both themes; accessibility check clean.

### 04.3 Run the scan worker in production

- **Status:** ⬜ open
- **Goal:** A systemd unit for the single scan worker, enabled by provisioning, restarted gracefully by the deploy; Redis persistence off for the scan database.
- **Depends on:** 04.1
- **Touches:** deploy/systemd/tabsira-worker.service, deploy/provision-app.sh, deploy/deploy.sh, deploy/provision-redis.sh, docs/OPERATIONS.md.
- **Done when:** `--dry-run` shows the worker steps; shellcheck and shfmt clean.
