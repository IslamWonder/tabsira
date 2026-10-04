# 14 · Deployment and operations

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 20:38 (Tunis)

Production at tabsira.me without Docker, with no downtime on deploy and data reachable only over the VPN.

| Step                                                  | Status | Notes                                                                                 |
| ----------------------------------------------------- | ------ | ------------------------------------------------------------------------------------- |
| Deploy scripts with rollback and no downtime          | ✅     | Ready; never run on a server yet.                                                     |
| Database and Redis host over the VPN, nightly backups | ✅     |                                                                                       |
| Scheduled jobs, UTC everywhere                        | ✅     |                                                                                       |
| Rehearsal on a scratch server                         | 🔄     | Rehearsed in local containers on 2026-10-04 18:04, real servers pending.              |
| First production deploy                               | ⬜     |                                                                                       |
| Delivery documents and the smoke scan checks          | ✅     | README, challenge log, operations section, rain scene and trial scan in `make smoke`. |

**Waiting on the owners**

- Production hosts, backup copy destination, Jenkins and Sonar details (owners).

**How we check it**

- Rehearsal, then a smoke test against tabsira.me.

## Tasks

### 14.1 Rehearse the deploy on a scratch server

- **Status:** 🔄 rehearsed in local containers on 2026-10-04 18:04, real servers pending; review before the first real deploy added the boot-order guard for the VPN address, the shared corpus folder and the full production template
- **Goal:** Provision a scratch app host and data host, deploy, roll back, restore a backup.
- **Depends on:** A scratch VM pair.
- **Touches:** deploy/ fixes only, docs/OPERATIONS.md.
- **Done when:** Every step works from the docs alone.

### 14.2 Copy backups off the data host

- **Status:** ⏸ waiting on owners
- **Goal:** Nightly copy of the database dumps to the owners' chosen place.
- **Depends on:** The destination.
- **Touches:** deploy/backup-db.sh, one timer.
- **Done when:** A restore from the copy works.

### 14.3 Delivery documents and the smoke scan checks

- **Status:** ✅ 2026-10-04 20:38 (the audit of 4 October listed them under task 14.2; numbered 14.3 here because 14.2 was already the backup copy)
- **Goal:** Close the delivery gaps of the wave 5 audit: `README.md` (v2 §30), `docs/CHALLENGE-LOG.md` with the delivery table, the cost, alternatives and content-review section of `docs/OPERATIONS.md`, the rain scene and one trial scan in `make smoke`, and the `make up` line of AGENTS.md saying what decision 20 decided.
- **Depends on:** 15.1
- **Touches:** README.md, docs/CHALLENGE-LOG.md, docs/OPERATIONS.md, scripts/smoke.sh, AGENTS.md (one line).
- **Done when:** `make smoke` passes on tabsira.test with the rain scene and a finished trial scan; the deck and the video are named as not in the repository.
