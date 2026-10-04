# 15 · Quality gates

**Phase:** 1 · **Priority:** High · **Status:** 🔄 · **Updated:** 2026-10-04 15:13 (Tunis)

Every change is tested; nothing merges below 100 % coverage.

| Step                                                | Status | Notes              |
| --------------------------------------------------- | ------ | ------------------ |
| 100 % coverage, lint and type checks on every merge | ✅     |                    |
| Code summary command (make stats)                   | ✅     |                    |
| Gold scenes evaluation (make eval)                  | ✅     | docs/EVALUATION.md |
| HTTP smoke test (make smoke)                        | ✅     | 2026-10-04 15:13   |

**How we check it**

- make lint, make coverage, make smoke.

## Tasks

### 15.1 HTTP smoke test

- **Status:** ✅ 2026-10-04 15:13
- **Goal:** `make smoke` checks the main pages and API routes of a running app, locally and against tabsira.me.
- **Depends on:** 04.1
- **Touches:** scripts/smoke (new), Makefile.
- **Done when:** Passes on tabsira.test; fails clearly when a route breaks.

### 15.2 Rewrite old commits without other projects' names

- **Status:** ⬜ main machine, end of phase
- **Goal:** Remove every mention from history once all branches merged.
- **Depends on:** All phase 1 branches merged.
- **Touches:** Git history only.
- **Done when:** No mention in any commit; owners push once.

### 15.3 Phase 1 test task: back to 100 %

- **Status:** ⬜ open, at the end of phase 1
- **Goal:** Write the tests that phase mode skipped (decision 42) and bring `make coverage` back to 100 % in web, API and vision before release.
- **Depends on:** All phase 1 feature tasks merged.
- **Touches:** Tests only, plus fixes for the bugs they find.
- **Done when:** `make lint && make coverage` pass on main; `make smoke` passes.

### 15.4 One command to set up a machine: `make bootstrap`

- **Status:** ⬜ open, ready now (the vectors step is `scripts/vectors/ensure.sh`, task 05.4)
- **Goal:** `make bootstrap` runs docs/SETUP.md end to end and skips every step whose data is already there: it checks before it imports (scripture counts, ontology and learning-path versions, `geodata.geonames` rows, vector counts), downloads the corpora, the GeoNames export and the vector archive from the owners' bucket when missing (URLs and paths from `.env`, with their `.sha256` checked), restores or imports, then prints the status table. `scripts/seed-geonames.sh` gains a guard that refuses to replace a populated table without `--force`.
- **Depends on:** — (the vectors part after 05.1).
- **Touches:** a new scripts/bootstrap.sh, the Makefile, scripts/seed-geonames.sh, scripts/data.sh, .env.example and the typed settings for the archive URLs, docs/SETUP.md.
- **Done when:** On a fresh machine `make bootstrap` gets to a working `http://tabsira.test`; run a second time, it imports nothing and finishes in under a minute; `make smoke` passes.

### 15.5 Local development over plain HTTP on port 80

- **Status:** ✅ 2026-10-04 18:34
- **Goal:** Serve `tabsira.test`, `api.tabsira.test` and `admin.tabsira.test` from nginx on port 80 without TLS (decision 49): cookies lose the Secure flag and the `__Secure-` prefix only where `SITE_URL` is http, production refuses http addresses, the setup script drops mkcert, the smoke test and the docs follow.
- **Depends on:** —
- **Touches:** nginx/local, scripts/setup-nginx-local.sh, scripts/smoke.sh, scripts/dev.sh, scripts/provision-dev.sh, .env.example, apps/api config and cookie services, docs.
- **Done when:** `make smoke` passes against `http://tabsira.test`; the cookie and config tests pass; security review passes.
