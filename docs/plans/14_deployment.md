# 14 · Deployment and operations

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 14:36 (Tunis)

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
