# 12 · Admin area

**Phase:** 1 · **Priority:** Medium · **Status:** ✅ · **Updated:** 2026-10-04 15:38 (Tunis)

A private area for the team at admin.tabsira.me, reachable only over the VPN.

| Step                                                      | Status | Notes                      |
| --------------------------------------------------------- | ------ | -------------------------- |
| Sign-in, optional two-factor, audit log                   | ✅     | Two-factor off by default. |
| Accounts, consents, ontology terms, learning path, places | ✅     |                            |
| Only on its own host, never from the public site          | ✅     |                            |
| Rulings queue (unblocks hadith in insights)               | ⏸      | Later admin work.          |

**Waiting on the owners**

- DNS provider and VPN DNS access for the certificate (owners).

**How we check it**

- Security review passed.

## Tasks

### 12.1 Rulings queue for editors

- **Status:** ⬜ open, ready now, high priority: no hadith can show in an insight until an editor records its ruling.
- **Goal:** An admin screen that lists the hadith waiting for a ruling (the queue the engine and `python -m src.cli.record_ruling` already use), shows each hadith's stored text read-only with its source, gives the editor the dorar.net search link to open in their own browser, and records the editor's ruling (grade, grader, dorar page link, note) through the same service the command line uses. Rulings are append-only and every action is in the audit log.
- **Depends on:** — (the queue and the ruling service are on main: `apps/api/src/cli/record_ruling.py` and the scripture rulings service it calls).
- **Touches:** `apps/api/src/admin/views/` (one new view), `apps/api/src/admin/registry.py`, `apps/api/src/admin/templates/` if needed, `docs/ADMIN.md`.
- **Done when:** An editor records a ruling on `admin.tabsira.test` and the hadith shows in a new insight; the server never calls dorar.net (decision 18); scripture text is never editable or copied into a ruling; tests for the record path; security and scripture reviews pass.

### 12.2 Moderation queue for reported posts

- **Status:** ⏸ phase 2, ready to start (the social API is on main)
- **Goal:** An admin screen for held and reported posts and comments, using `moderation_service.approve`, `reject` and `remove`; a moderator's own words are never shown to the author.
- **Depends on:** —
- **Touches:** `apps/api/src/admin/views/` (one new view), `apps/api/src/admin/registry.py`, `docs/ADMIN.md`.
- **Done when:** A report can be decided from `admin.tabsira.test`; every decision is in the moderation log and the audit log; security review passes.

### Rules for both

- Admin runs only on `admin.tabsira.me` (decision 38); the panel is in English, left to right; Arabic content shows in its own direction.
- Never name another project of the owners; the commit hooks refuse it.
- On the main machine, tests use at most two workers and full checks run under `flock /tmp/tabsira-gate.lock`.
