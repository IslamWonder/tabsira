# 14 · Deployment and operations

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 14:51 (Tunis)

Production at tabsira.me without Docker, with no downtime on deploy and data reachable only over the VPN.

| Step                                                  | Status | Notes                             |
| ----------------------------------------------------- | ------ | --------------------------------- |
| Deploy scripts with rollback and no downtime          | ✅     | Ready; never run on a server yet. |
| Database and Redis host over the VPN, nightly backups | ✅     |                                   |
| Scheduled jobs, UTC everywhere                        | ✅     |                                   |
| Rehearsal on a scratch server                         | ⬜     |                                   |
| First production deploy                               | ⬜     |                                   |

**Waiting on the owners**

- Production hosts, backup copy destination, Jenkins and Sonar details (owners).

**How we check it**

- Rehearsal, then a smoke test against tabsira.me.

## Tasks

### 14.1 Rehearse the deploy on a scratch server

- **Status:** ⬜ open
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
