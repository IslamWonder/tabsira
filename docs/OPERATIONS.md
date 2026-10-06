# Operations

How TABSIRA runs in production, and how to deploy, roll back and provision it. No Docker in production (decision 20): systemd, gunicorn, pm2, nginx.

Everything below lives in `deploy/` and `nginx/production/`. No real host, address, key or password is in git; the owners supply them (see [What the owners must supply](#what-the-owners-must-supply)). Production files never contain the development domain.

## Topology

```text
Internet ──► app host (public)                         data host (no public service)
             nginx :443  tabsira.me, api.tabsira.me      PostgreSQL 18  :5432 ┐ wt0 + loopback only,
             pm2  web   127.0.0.1:3000                   Redis          :6379 ┘ app host's VPN address only
             gunicorn   127.0.0.1:8000  ── Netbird VPN (wt0) ──►
             vision     127.0.0.1:8100
             timers     sync-quran, audit-retention, reconcile-photos, mark-orphans
Admins ──► Netbird DNS ──► app host VPN address :443  admin.tabsira.me (VPN only)
```

| Piece                      | Where                                         | Run by                                |
| -------------------------- | --------------------------------------------- | ------------------------------------- |
| web (`apps/web`)           | `current/web`, pm2 app `tabsira-web`, cluster | pm2, started at boot by `pm2-<user>`  |
| API (`apps/api`)           | `current/apps/api`, `tabsira-api.service`     | systemd, gunicorn and uvicorn workers |
| vision (`services/vision`) | `current/services/vision`, `tabsira-vision`   | systemd, one worker, `127.0.0.1:8100` |
| scan worker (`apps/api`)   | `current/apps/api`, `tabsira-worker.service`  | systemd, exactly one process, no port |
| daily Quran sync           | `tabsira-sync-quran.timer`                    | systemd, 02:30 UTC, one process       |
| audit retention policy     | `tabsira-audit-retention.timer`               | systemd, 03:40 UTC, one process       |
| public photo copies        | `tabsira-reconcile-photos.timer`              | systemd, hourly, one process          |
| orphaned atlas entries     | `tabsira-mark-orphans.timer`                  | systemd, 04:10 UTC, one process       |
| database dumps             | `tabsira-pg-backup.timer` on the data host    | systemd, 03:15 UTC                    |
| IndexNow                   | last step of `deploy.sh`, production only     | the deploy, never a timer             |
| error tracking             | GlitchTip, only when `GLITCHTIP_DSN` is set   | the API (decision 24)                 |

Scheduled work runs in exactly one process: timers on the one application host, never a thread in each worker.

## Layout on the application host

As on the earlier prototype: the clone is the application, and only the web builds live elsewhere.

```text
/opt/tabsira                       the git clone: the API, the scan worker and vision run from it,
                                   in place; deploys run from it (cd /opt/tabsira && ./deploy/deploy.sh)
/opt/tabsira/.env                  production environment (0600, owned by devops, ignored by git)
/opt/tabsira/data/corpus           the two corpus files, only to rebuild the store from its sources (ignored by git)
~/tabsira-data/{corpus,geodata,vectors}  the verified archives load-data.sh downloads once
/srv/tabsira/web/releases/<id>     each web build's own copy (UTC time and short commit)
/srv/tabsira/web/current           symlink to the live web build; previous: the one before
/srv/tabsira/web/deployed-commits  the commit each deploy left serving (for --rollback)
/srv/tabsira/static/_next/static   every recent build's static files, served by nginx
/var/log/tabsira                   web logs (pm2); the API and timers log to the journal
```

The web build has its own copy because Next.js reads its build while it runs: building in the clone while the live processes read it would break pages mid-deploy. The API, the worker and vision need no copy: a worker imports the code once, when it starts, and the roll replaces the workers one at a time.

## Provisioning

Order matters: the data host first, because the first deploy migrates the database.

1. **Netbird** on both hosts (interface `wt0`). Note each host's VPN address. The scripts read the interface from `VPN_IFACE` (default `wt0`) and fail with "No address on wt0" when it is missing; on a machine without Netbird name the interface that carries the private network and pass `DATA_HOST_VPN_IP`.
2. **Database host and Redis host.** `deploy/provision-postgres.sh` and `deploy/provision-redis.sh` are standalone, like the earlier prototype's installers: copy the one file to its host and run it as root; neither needs the repository. Each is idempotent, `--check` prints the plan and changes nothing, and each ends by printing the lines for the application host's `.env`, passwords included.

   ```bash
   # database host (db.tabsira.me)
   sudo ./provision-postgres.sh --check
   sudo APP_HOST_VPN_IP=<app host VPN address> ./provision-postgres.sh   # without it: the VPN subnet

   # Redis host (redis.tabsira.me)
   sudo ./provision-redis.sh --check
   sudo ./provision-redis.sh
   ```

   Neither manages the firewall: allow 5432 and 6379 from the application host in the firewall you use. When both run on one data host, `deploy/provision-data.sh` (from a checkout) runs the two and adds the `ufw` rules described below.

   It installs PostgreSQL 18 with PostGIS, pgvector and TimescaleDB, creates the role `tabsira` and the database `tabsira` with `search_path = app, geodata, public` and the nine extensions (`postgis`, `vector`, `timescaledb`, `pg_trgm`, `unaccent`, `pgcrypto`, `btree_gin`, `btree_gist`, `pg_stat_statements`), and installs Redis 8 with a password and protected mode. Both listen on `127.0.0.1` and the `wt0` address only (`DATA_HOST_VPN_IP` to name it). The script first sets `net.ipv4.ip_nonlocal_bind=1` (`/etc/sysctl.d/90-tabsira-nonlocal-bind.conf`), so a reboot that starts them before Netbird has given the address does not leave them down. `pg_hba.conf` has one managed block: the application role from `APP_HOST_VPN_IP/32` with `scram-sha-256`, no ranges, no trust. The firewall step adds `ufw` rules that allow 5432 and 6379 from the app host on `wt0` and deny them elsewhere; it does not enable `ufw` (a wrong default over ssh locks you out) unless `FIREWALL_ENABLE=true`. Passwords are generated into `/etc/tabsira/postgres.env` and `/etc/tabsira/redis.env` (root only); each script ends by printing the lines to paste into the application host's `.env`: `DATABASE_URL` and `SYNC_DATABASE_URL` with the generated password in them (48 hex characters, so no escaping), and for Redis `REDIS_URL` without a password plus `REDIS_PASSWORD`. `sudo deploy/show-env-lines.sh` prints all four again from the root-only files. Treat that output as a secret. The API refuses a Redis URL that carries a password.

3. **Application host** (on the host itself, with sudo, from the clone at `/opt/tabsira`; the script finds this host's Netbird address on `wt0` itself):

   ```bash
   sudo CERTBOT_EMAIL=<address> \
     APP_REPO=<git url> deploy/provision-app.sh --dry-run
   ```

   Run it without `--dry-run` once the plan reads right. The certificates are issued by certbot during the run, so the three names must already resolve to this host. A certificate that exists (made with `certbot` by hand) is kept. Where they cannot yet (a rehearsal, a host before the DNS change), run it with `--skip-tls`: it does everything else but the certificates and `apply-config.sh`. Put a certificate and its key at `/etc/letsencrypt/live/<name>/{fullchain,privkey}.pem` for `tabsira.me`, `api.tabsira.me` and `admin.tabsira.me` (self-signed ones will do for a rehearsal), then run `APP_HOST_VPN_IP=<this host's VPN address> deploy/apply-config.sh` as root. Do not leave self-signed files where certbot will write: delete `/etc/letsencrypt/live/<name>` before the real issue. It uses the existing `devops` account (the one that ran `sudo`; it creates it when missing), builds the clone at `/opt/tabsira` and the web folders under `/srv/tabsira`, installs in that user's home nvm, the Node of `.nvmrc`, the pnpm that `package.json` pins, pm2 (started at boot), uv and the Python of `apps/api/.python-version` (`deploy/install-toolchain.sh`, pinned versions, `--check` to preview; run as the app user, it also installs with sudo the system tools the data and deploy scripts call when missing: the PostgreSQL 18 client with `psql` and `pg_restore`, curl, tar, gpg, git and the build tools; safe to run again), nginx, certbot, the narrow sudoers file and `/usr/local/bin/tabsira-deploy`, and applies `deploy/apply-config.sh`. It writes `/opt/tabsira/.env` from `deploy/env.production.example` when none exists and generates `HASH_SECRET`; every other `CHANGE_ME` is left for the owners.

4. Fill `/opt/tabsira/.env` (every `CHANGE_ME`, the S3 keys of [Photos](#photos), `REDIS_PASSWORD`). Then check the data host from the application host before the first deploy: `psql "<the DATABASE_URL without +asyncpg>" -c 'select current_user'` must answer (the data host cannot test this login itself, `pg_hba` admits the application host only), and Redis must refuse a client without the password. Then, as devops: `cd /opt/tabsira && ./deploy/deploy.sh --check`, `./deploy/deploy.sh --dry-run` and `./deploy/deploy.sh`. The first deploy builds the web app, installs the Python environments and downloads the detector weights (about 630 MB, once; written from the scripts, not exercised in the rehearsal); the first build takes a few minutes. Later deploys can name the parts to update, for example `./deploy/deploy.sh api web` (`api` brings the migrations and the scan worker; the others are `worker`, `vision`, `web`); with none named, all of them.
5. After the first deploy, as the app user: `deploy/load-data.sh`. The database has four schemas: `app` and `corpus` (the reference data, decision 57) filled by the app chain, `geodata` and `vectors` with one chain each; the first deploy migrated them and this fills them, in this order, each once only: GeoNames, the corpus (the scripture store, the world ontology and the learning path), the scripture vectors. Nothing is fetched from the third-party sources: each comes from the owners' bucket and is checked against its `.sha256` before it is imported (docs/CORPUS.md, docs/EMBEDDINGS.md), downloaded once into `~/tabsira-data/`. The corpus import checks every verse and hadith against its stored hash and every table against the archive's manifest, in one transaction. GeoNames is loaded by default from one of two sources, `--geonames-source=dump|geonames` (or `GEONAMES_SOURCE` in the `.env`): `dump`, the default, is the verified snapshot of 2026-10-04 (about 340 MB); `geonames` runs the original import, `scripts/seed-geonames.sh`, for fresh data from geonames.org, but downloads about 600 MB and takes about 15 minutes. `--no-geonames` leaves GeoNames out. The script checks the schemas and the nine extensions, runs `scripts/data.sh` from the clone, and ends by counting what the schemas hold (6,236 verses, hadiths, annotations, signals, ontology, the active learning path, vectors covering the store, places) and failing when a count is wrong. `--check` only prints the state. Data that is there is left alone; `--force` installs it again (replacing the corpus is refused while editor rulings or learners' states point at it). The two corpus files in `/opt/tabsira/data/corpus/` are needed only when `CORPUS_ARCHIVE_URL` is set to empty, to rebuild the store from its sources. Then `cd /opt/tabsira/apps/api && UV_NO_SYNC=1 uv run python -m src.cli.make_admin <email>` makes an existing account the first admin (`docs/ADMIN.md`). Keep `UV_NO_SYNC=1` on every `uv run` in the clone: without it uv installs the development dependencies into the production environment.

## Checking the host before a deploy

`deploy/deploy.sh --check` (also `deploy/check.sh`) is a read-only readiness check in plain shell. It needs no build and no Python environment, so it runs before the first deploy. It reports the tools on the application user's PATH (node of `.nvmrc`, pnpm, pm2, uv), the clone at `/opt/tabsira` and the web folders under `/srv/tabsira`, the installed units and sudoers file, whether `deploy/apply-config.sh --check` finds the host in step with the checkout, the environment file (mode 0600, `ENVIRONMENT=production`, no placeholder, no development address, every required key set), whether the data host's database and Redis ports accept connections and the database accepts this login, and each Let's Encrypt certificate (present, names its host, not about to expire, renewed through the webroot). Each line is `ok`, `fix` (the exit status is 1) or `check`. The provisioning scripts take `--check` as another name for `--dry-run`.

## Checking the environment file

`python -m src.cli.check_config` loads the settings (which already refuse a development host, an empty key or a short secret in production) and, when `ENVIRONMENT=production`, prints the production checklist: every setting an operator reads before a deploy, grouped by what it is for, each line `ok`, `fix` (required: the exit status is 1 and the deploy stops), `check` (recommended) or `off` (optional). Secrets are never printed. It covers, among others: every key of `deploy/env.production.example` present in the file (a key the code gained and the owners never set is a `fix`; a key the example does not know, misspelt or removed, is a `check`), no `CHANGE_ME` or address placeholder left, one domain for the site, the API and the admin host, `CORS_ORIGINS` and the cookie domain, `SYNC_DATABASE_URL` naming the same database, password lengths, `API_WORKERS` against the connection budget, a model for every AI stage of the active provider (a blank `AI_*__PLANNER_MODEL=` line overrides the default with nothing), the mail server, the Google callback, the baked `NEXT_PUBLIC_*` addresses and the pm2 settings.

The Turnstile line (`TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY`, recommended) is `ok` when both keys are set; both empty switches the bot check off, and one without the other stops the API at start. With `--live` and a secret set, a dummy token is posted to Cloudflare, which answers `invalid-input-response` to a good secret and `invalid-input-secret` to a bad one; only the latter is reported as a failure, and the secret is never printed.

`--live` also tries the services: the database, Redis (the password, and that it keeps nothing on disk), the AI provider's key (a listing of its models: no tokens spent), the detector, the mail server (a login, never a message) and that this host resolves the site and the API names. `--env-file PATH` checks another file. The deploy runs it in a new release before the migrations; run it by hand from any release:

```bash
cd /opt/tabsira/apps/api && UV_NO_SYNC=1 uv run python -m src.cli.check_config --live
```

## Deploying

As devops, from the clone, as on the earlier prototype:

```bash
cd /opt/tabsira
./deploy/deploy.sh --check              # read-only: tools, clone, web folders, .env, database, Redis, certificates
./deploy/deploy.sh --dry-run            # print every step with its values, run nothing
./deploy/deploy.sh                      # deploy origin/main
./deploy/deploy.sh --rollback           # back to the commit deployed before this one
```

`/usr/local/bin/tabsira-deploy` does the same from anywhere (Jenkins calls it over ssh). The steps:

1. Take the lock; check the host and that `.env` says `ENVIRONMENT=production` and names no development address.
2. Optional dump (`PRE_DEPLOY_BACKUP=true`).
3. Record the commit that serves now, fetch, and reset the clone to its upstream branch (`git reset --hard @{u}`); then run again from the updated copy, so the steps below are always the latest.
4. `uv sync --frozen --no-dev` for the API and vision, `pnpm install --frozen-lockfile`, the detector weights (once).
5. `check_config --live`: the production checklist of the environment file, and each service tried for real (see [Checking the environment file](#checking-the-environment-file)); a `fix` line stops the deploy here, before anything is migrated. Then the migrations: the `geodata`, `app` and `vectors` chains (`scripts/migrate.sh`), then the audit policy.
6. Build the web app (`NEXT_PUBLIC_*` are baked here from `.env`; the build refuses a development address).
7. The API: boot the new code once on a spare port (18000) and wait for `/health/ready`, then replace the workers one at a time. Then restart the scan worker, and vision when `services/vision` changed.
8. The web (`deploy/web-roll.sh deploy`): copy the build to `/srv/tabsira/web/releases/<id>`, add its static files to `/srv/tabsira/static`, boot it once on a spare port (3100), switch `current`, reload the pm2 instances one at a time.
9. Health gate; compare the host's nginx and units with the clone (a warning); IndexNow (`node scripts/indexnow.mjs`, production only, never fails the deploy).

On a failure after the pull the clone goes back to the recorded commit, the dependencies are installed again, the API and worker are rolled again and the web goes back to its previous build. **Migrations are not reverted**: write migrations that the previous code can run against (add before you remove), and restore a dump (`deploy/restore-db.sh`) only as a last resort.

### The scan worker

`tabsira-worker.service` runs `python -m src.cli.scan_worker` from the clone (`/opt/tabsira/apps/api`), as the application user, with the API's `.env` (including `REDIS_URL` and `REDIS_PASSWORD`). It is the only consumer of the scan queue: never start a second one, and never run it inside the API workers. `deploy/apply-config.sh` installs and enables it (`provision-app.sh` runs that); the sudoers file lets the deploy user restart and status it.

The deploy restarts it right after the API rolls, once the migrations have run. A restart is a `SIGTERM`: the worker stops taking jobs, lets running scans finish for up to `SCAN_JOB_TIMEOUT_SECONDS` (240 s), then exits. `TimeoutStopSec=300` covers that, so a deploy can wait up to five minutes for the worker; raise `TimeoutStopSec` if you raise the job timeout. A restart does not drop in-flight jobs: the queue is idempotent, a job that was cut short stays unacknowledged on the Redis stream and is delivered again (after ten minutes), and running a scan twice changes nothing. `Restart=on-failure` brings it back after a crash. A rollback restarts it onto the previous commit the same way.

Check: `systemctl status tabsira-worker`, `journalctl -u tabsira-worker -f`. Rehearse without changing anything: `deploy/deploy.sh --dry-run` prints the restart step, `deploy/provision-app.sh --dry-run` the sudoers line, `sudo deploy/apply-config.sh --dry-run` the unit file to install.

### Redis persistence is off

The scan workflow keeps each photo in Redis, sealed with AES-GCM (the key comes from `HASH_SECRET`, which Redis never holds) and expiring after `SCAN_IMAGE_TTL_SECONDS` (one hour), next to the job queue and the progress events, all in the one database of `REDIS_URL`. Redis can switch persistence on or off only for the whole instance, not per database, so `deploy/provision-redis.sh` turns it off: `appendonly no` and `save ""`, and it deletes any `dump.rdb` or `appendonlydir` an earlier run left. The other option, keeping persistence because the photos are sealed and expire, was rejected: a photo is the most sensitive thing we hold, and the safest copy on disk is none. The price is that a Redis restart empties the queue, the progress events and the rate-limit counters: a scan caught by it fails and the person scans again. Everything that must last is in PostgreSQL. Check with `redis-cli CONFIG GET appendonly` (`no`) and `CONFIG GET save` (empty). `deploy/provision-redis.sh --dry-run` prints the persistence line.

### The API roll (gunicorn)

`deploy/api-roll.sh` replaces the workers one at a time. The unit starts gunicorn from the clone (`/opt/tabsira/apps/api`, its `.venv`), so a worker forked after the deploy has reset the clone imports the new code. For each running worker: `TTIN` adds one, the script waits until it has stayed up for eight seconds and `/health/ready` answers, then `TTOU` retires the oldest, which finishes its requests within `--graceful-timeout` (30 s). At least N workers serve at every moment. Afterwards the pool is brought to `API_WORKERS`.

A first start, or a changed Python, is a `systemctl restart tabsira-api` (workers keep the master's interpreter).

### The web roll (pm2)

`deploy/web-roll.sh` puts the new build live. `deploy/ecosystem.config.cjs` runs `/srv/tabsira/web/current/apps/web/server.js` in cluster mode (`WEB_INSTANCES`, default 2), with the environment of `/opt/tabsira/.env`. `pm2 reload` runs one instance at a time; each must be online, up for five seconds and answer before the next is touched. Five builds are kept; the shared static folder keeps the files of older builds for seven days, because a tab opened before a deploy still asks for the old chunk names. `deploy/web-roll.sh rollback` puts the previous build back the same way.

## nginx and TLS

`nginx/production/tabsira.me.conf` and `nginx/production/snippets/` are installed by `sudo deploy/apply-config.sh` (also `--check` and `--dry-run`). It also installs the same `ip_nonlocal_bind` setting and a systemd drop-in that starts nginx after `netbird.service`: the admin block listens on the VPN address only, and without them a reboot that brings nginx up before Netbird leaves the whole site down. It builds every file aside, installs them, runs `nginx -t`, and **restores the previous files and does not reload when the test fails**. The deploy user cannot write `/etc`, so `deploy.sh` only warns when the host differs.

- Security headers live in snippets that every location that sets a header includes (a location that uses `add_header` drops the server block's headers). HSTS, a CSP for the web host that allows only the map tiles, Google Analytics 4 and Microsoft Clarity (injected after consent), `client_max_body_size 16m` for photos.
- `limit_req` on the open POST routes (`/auth/login`, `/auth/signup`, `/support`, `/consent`, `/client-errors`), and on `/atlas/` (zone `tabsira_atlas`, 10 requests a second per address, burst 30: the map's window, cluster and list reads are spatial queries, and the API cuts each at 3 seconds with a 503). nginx caches and serves no photo; public photos from the bucket or a CDN carry `Cache-Control: public, max-age=300`, never longer.
- The API trusts proxy headers from `127.0.0.1` only (`forwarded_allow_ips` in `deploy/gunicorn.conf.py`, handed to uvicorn), so the rate limit and the audit log see the visitor's address.
- No OCSP stapling: Let's Encrypt no longer issues OCSP responders.
- Three certbot lineages, one per host: `tabsira.me` (with `www`), `api.tabsira.me` and `admin.tabsira.me`, each by an HTTP challenge through the webroot `/var/www/certbot` (`certbot certonly --cert-name NAME -d NAME`), renewed by `certbot.timer` with a deploy hook that runs `nginx -t` before it reloads. A lineage made with `certbot --nginx` renews through the nginx plugin, which cannot find the admin name: `provision-app.sh` moves it to the webroot (`certbot reconfigure`), and `deploy/check.sh` says when one still renews through nginx. `tabsira.me`'s certificate should name `www.tabsira.me` too (`--expand`); `apply-config.sh` warns when it does not. The admin name answers port 80 for the challenge only; the admin area is on the VPN address.

### The admin host

The admin area is served only at `https://admin.tabsira.me`, over the VPN.

- A separate server block listens on the app host's VPN address only (`APP_HOST_VPN_IP`, generated into `tabsira-admin-listen.conf`) with `allow <VPN subnet>; deny all;` as a second guard (`VPN_SUBNET`, default `100.64.0.0/10`, Netbird's own range). It proxies `/admin` to the API with `Host: admin.tabsira.me`, redirects `/` to `/admin/`, sets `no-store` and `frame-ancestors 'none'` (`docs/ADMIN.md`), and rate limits `/admin/login` to thirty requests a minute per address.
- `api.tabsira.me` answers 404 for `/admin` and everything under it. The API also refuses `/admin` on any host but `ADMIN_URL`.
- **DNS.** No public record exists for `admin.tabsira.me`. In the Netbird dashboard add a DNS nameserver entry (split DNS) for the domain `admin.tabsira.me`, or a custom zone with an A record, that resolves it to the app host's VPN address, and distribute it to the admins' peer group.
- **TLS.** The admin certificate is a lineage of its own, issued by an HTTP challenge, so `admin.tabsira.me` needs a public A record for issuing and renewing it; nginx serves the admin area on the VPN address only, and port 80 answers the challenge and nothing else. For a host with no public record, set `CERTBOT_DNS_PLUGIN` and `CERTBOT_DNS_CREDENTIALS` and `provision-app.sh` issues it by DNS-01 instead.
- Locally, `admin.tabsira.test` is added by `scripts/setup-nginx-local.sh` (plain HTTP on port 80, `/etc/hosts` line) and answers this machine only.

## Backups

On the data host `tabsira-pg-backup.timer` runs nightly at 03:15 UTC (`/usr/local/bin/tabsira-pg-backup`): a custom-format dump of `tabsira` into `/var/backups/tabsira`, verified with `pg_restore --list`, plus a globals file (roles and their `search_path`). Dumps older than 14 days are deleted, but the newest three are always kept (`BACKUP_KEEP_DAYS`, `BACKUP_KEEP_MIN`). Run one now: `systemctl start tabsira-pg-backup.service`, or `deploy/backup-db.sh` as root (it runs itself as `postgres`). `deploy/backup-db.sh --url <url>` takes one from the app host before a risky deploy (`PRE_DEPLOY_BACKUP=true`); the application user cannot write `/var/backups`, so that dump goes to `~/backups/tabsira` (`BACKUP_DIR` overrides it), on the application host, which the loss of the data host does not touch but a compromise of the application host does. `pg_dump` prints a warning about circular foreign keys on `continuous_agg`: it belongs to TimescaleDB's own catalog, and the restore script handles it.

These are local copies: they do not survive the loss of the data host. Copying `/var/backups/tabsira` off the machine is the owners' decision (listed below).

Restore, on the data host as root: `deploy/restore-db.sh <dump>` restores into a new database (`tabsira_restore`) owned by the application role, so the live one is never overwritten by accident; check it there. `--into tabsira --yes-overwrite` drops the live database and restores into its place. PostgreSQL refuses to drop a database that has sessions, so stop the API and the scan worker on the application host first (`sudo systemctl stop tabsira-worker tabsira-api`, as root; the sudoers file allows restart, start and status only) and start them again afterwards; a refused drop changes nothing. Everything written after the dump is lost. The restore only brings back the database: the role, its password and its `search_path` come from the provisioning (the globals file is there for a lost data host).

## Photos

Decision 44. Production keeps consented photos in a private S3-compatible bucket and nowhere else: `STORAGE_BACKEND=s3` with every `S3_*` key (`deploy/env.production.example`). The environment file is refused at start when the resolved backend is not S3, when a key is missing, or when an `S3_*` key is set without `S3_BUCKET`.

- **Start-up check.** The API will not start in production when it cannot use the bucket. At boot it probes with a 5-second timeout: a HeadBucket, then a put of a small probe object in a random account's folder (`private/users/<random uuid>/insights/<random>.jpg`), a listing of that folder, and its deletion one by one and by batch. That proves the keys can do everything an account deletion needs; a failure names the bucket, the endpoint and the step, never a key.
- **Bucket permissions.** The keys need, on the bucket: `s3:ListBucket` (with the `private/users/` prefix at least), and on its objects `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` (which also covers the multi-object delete). Without `ListBucket` the probe fails at `ListObjectsV2`: without it every account deletion and every withdrawn photo consent would answer 503, because each one empties the account's folder. The client sends a request checksum only where an operation requires one, since some S3-compatible providers refuse the CRC32 checksums boto3 adds by default.
- **Check by hand.** `python -m src.cli.check_config` runs the same probe and prints `storage: ok` or `storage: FAILED, <reason>` (exit 1 in production); run it with the production environment file after changing any `S3_*` key.
- **Development and test.** With no `S3_BUCKET`, photos go to `LOCAL_MEDIA_DIR` (`data/media` of the checkout by default) and the API logs "No S3 bucket: photos go to `<dir>`; production requires S3". A failing probe is a warning there, never a refusal, so `make dev` works offline.
- **A deletion the store refused.** A withdrawal or a moderator's removal answers the person even when the store fails; the public copy it should have deleted is then reconciled: the API asks the scan worker (`photos.reconcile`, run 30 s later in that one process), and `tabsira-reconcile-photos.timer` runs `python -m src.cli.reconcile_photos` every hour, which deletes every public copy nothing shows any more and exits 1 while the store still refuses one. Two runs never overlap (an advisory lock). Run one now: `systemctl start tabsira-reconcile-photos.service`.
- **Orphaned atlas entries (decision 60).** `tabsira-mark-orphans.timer` runs `python -m src.cli.mark_orphans` daily at 04:10 UTC, on the one application host and never in a worker. It turns published atlas entries that nobody sponsors and that had no sign of life for `ORPHAN_AFTER_DAYS` (30) into `orphaned`, widens their public place for good and prints counts only (`orphans: N entries orphaned, M places widened, F failed`). It exits 1 when an entry failed (it is tried again the next day) and does nothing while the `atlas` or `atlas_sponsorship` feature is off, so an entry nobody can sponsor keeps its place. A second run the same day changes nothing. The unit runs the clone's own virtual environment (no uv, no cache to write) with a read-only file system except `data/` (a host that keeps photos on disk), read-only home, no devices, no kernel tunables, modules or logs, and only IP and Unix sockets. Run one now: `systemctl start tabsira-mark-orphans.service`. The API's nginx access log for `/atlas/` has no query string (the `tabsira_noquery` format, because `GET /atlas/orphans` carries a position); the error log still records the request line, query included, for a 502 or 504, so keep the error logs on their short rotation and never ship them elsewhere.
- **Serving.** No route serves stored photos yet, so nginx has no location for them. Published copies are served from `S3_PUBLIC_BASE_URL` with `Cache-Control: public, max-age=300`; private photos only through signed links. The web pages' Content-Security-Policy must allow that origin in `img-src`, or the browser refuses every published photo: `deploy/apply-config.sh` reads `S3_PUBLIC_BASE_URL` from the production `.env` and writes its origin into `tabsira-headers-web.conf`, so after setting or changing it run `sudo deploy/apply-config.sh`.
- **Sound effects.** The 1,000 MP3 files of the ontology (one per entity, `E001.mp3` to `E1000.mp3`) are static files, not photos. Upload them once to the same bucket under `static/ontology/audio/`, for example `aws s3 sync out/ontology/audio/ s3://<bucket>/static/ontology/audio/ --content-type audio/mpeg`. The API reads them with the bucket's own keys and serves them at `GET /sounds/ontology/<id>` with `Cache-Control: public, max-age=86400`, so the bucket stays private and the browser talks to the API only. Nothing under `static/` is ever a photo. With no bucket, the same path under `LOCAL_MEDIA_DIR` is read (`data/media/static/ontology/audio/` by default). A missing file is a 404 and the page plays nothing.

## Basiras published before decision 68

Once, after the deploy that brings decision 68: every basira that is a public page or a published atlas entry and has no post gets its post, public and with no reflection, with the photo only where its owner chose to show it. It skips orphaned entries, withdrawals, accounts that are closed, unverified or without a handle, and counts what it skipped. Safe to run again.

```bash
cd apps/api && uv run python -m src.cli.publish_missing_posts --dry-run --i-understand --allow-production   # count
cd apps/api && uv run python -m src.cli.publish_missing_posts --i-understand --allow-production             # publish
```

## Mock members

The platform starts with about 1000 mock members (decision 66, plan 23). `tools/mockdata` writes `tabsira-mock-v1.json` to `../tabsira-data/mock/`; the owners upload it to their bucket (never committed). The importer reads it from a path or from `s3://bucket/key` with the same `S3_*` keys as the photos (no new setting).

The file is made on a development machine in three steps (`tools/mockdata/README.md`): `make mock-photos` runs the real pipeline over the placepix photos into `photo-library.json`, `make mock-data` builds the members and their activity from the photos that gave an insight, and `make mock-texts` writes the posts' reflections and comments, checks the file with the importer's checks and writes `process-report.json` beside it. They read the development database and never write to it.

One command does it all, on a development machine or a host (like `make data`, it checks before it writes):

```bash
scripts/mock-data.sh import --allow-production    # on production: downloads the published file
scripts/mock-data.sh import                       # a development machine: ../tabsira-data/mock/tabsira-mock-v1.json if present
scripts/mock-data.sh reset --allow-production     # clean, then import again
scripts/mock-data.sh clean --allow-production     # remove every mock row (stops if real members depend on them; --also-dependent-rows removes those too)
scripts/mock-data.sh fill-in views --allow-production # a later feature onto the mock rows already imported (tools/mockdata/README.md)
scripts/mock-data.sh refresh --allow-production    # rewrite the imported mock insights from a patched file, keeping their posts (tools/mockdata/README.md)
scripts/mock-data.sh backup                       # dump the app schema only
scripts/mock-data.sh status                       # how many mock members, insights, posts
```

- Without a source the script reads `MOCK_FILE`, then the local file, then the published file `https://s3-v2.riastorage.com/tabsira/mock/tabsira-mock-v1.json` (an `https` address, a path or `s3://bucket/key` may also be given). A downloaded file is removed when the script ends.
- `import`, `reset`, `clean`, `fill-in` and `refresh` first dump the `app` schema to `<data>/backups/app-<UTC time>.dump` (`<data>` is `../tabsira-data` beside the checkout, else `~/tabsira-data` as on a host, or `TABSIRA_DATA_DIR`) (members and everything they own; the `corpus`, `geodata` and `vectors` schemas are large and reinstall from their archives), unless `--no-backup` is given. Restore with `pg_restore --clean --if-exists --schema=app -d <database> <file>`.
- An atlas entry whose point resolves to a GeoNames place of another country than its member's (a point near a border) is left out and counted in the report.

`import` and `reset` first apply any missing migration and stop when the scripture store, the hadiths or GeoNames are not installed. The Make targets call the importer directly:

```bash
make mock-import MOCK_FILE=../tabsira-data/mock/tabsira-mock-v1.json
make mock-import MOCK_FILE=s3://<bucket>/mock/tabsira-mock-v1.json MOCK_ARGS=--allow-production   # on production
make mock-clean MOCK_ARGS=--allow-production                                                      # remove every mock row
make mock-fill-in MOCK_FILL_IN=views MOCK_ARGS=--allow-production                                     # fill in a later feature, no backup
```

- Both commands pass `--i-understand`; the importer refuses without it, refuses a database named `tabsira_template` or ending in `_test`, and refuses `ENVIRONMENT=production` unless `--allow-production` is also given. The file is read from a path or from S3 up to 64 MB; a larger one is refused before it is read.
- Before anything is written it refuses a file of another version or a wrong shape (an id outside 1 to 10^9, a member under 13), refuses the whole file if any text, member name or handle fails the scripture guard, or any reflection, comment or sponsor note fails the app's own text checks (control characters, length, a link, an address or a number to call), and skips (and lists) an insight whose verse or hadith is not in the store.
- The import is one transaction and is idempotent by the reserved address `<handle>@mock.tabsira.me`: a second run creates nothing for a member that exists (an address of the earlier `mock.tabsira.invalid` domain counts too). A member's insights, posts, entries and everything else are written only when that member is created in the run.
- **The accounts are complete and work.** Every member is active, e-mail verified, has accepted the terms and the privacy text at the versions in force (no prompt to accept again), has its profile completed (goals, knowledge level, age range, religious background, gender, theme, motion, sound, `photo_storage_consent` on, a public name, some with the full-name consent), and signs in with the password `tabsira`, hashed by the app's own function with the configured rounds. The shared password is the owners' decision for the contest's judges: **production is reset at launch** (`reset`, or `clean` and a fresh import, then a different way to keep the accounts, or none). Those fields stay private as for every member. The mailer never sends to `@mock.tabsira.me` (nor to the old `.invalid` domain): `email_service.deliver`, the one place mail leaves the application, refuses it.
- **Every feature, whatever the switches.** The services run with every feature on, so the rows are the same on a host that has turned the network, the atlas or comments off: posts for everyone and for followers only, with and without a photo or a reflection, both reactions (`post_reactions`), bookmarks, follows, a few blocks, comments and one-level replies, atlas entries (about a tenth orphaned by the daily job's own function, with their generalisation rows, half of those then sponsored, each sponsor with a note), completions through the same functions the first «تمّ» uses (world places, reveals, evidence exposures, at the times of the file, so the practice streaks are real), and insight ratings kept as reviewed. No report, no moderation action by a person: the admin queue is empty. The moderation log is append-only, so the one row the job writes when it gives a widened entry its new id (`superseded_at_widening`) stays after `--clean`.
- Rows go through the application's services: the public point of an atlas entry is the approximate cell (`GEO_APPROX_CELL_METERS`), the exact point stays private. Photo keys are `https://placepix.net/id/<n>/<w>/<h>` addresses, shown as is and never passed to the photo storage. The moderation log is append-only, so the import writes no row to it.
- `--clean` deletes every account on `@mock.tabsira.me` (and on the old `.invalid` domain), which removes by cascade everything they own, plus the evidence exposures and the reports that name their posts, comments, entries and sponsor notes. It calls no storage. **Before deleting it counts what other members wrote that hangs on mock accounts** (their comments and replies under mock posts and comments, reactions, bookmarks, follows, blocks, sponsorships of mock entries, reports of mock content), prints the counts and stops: pass `--also-dependent-rows` to remove those too. It touches no other account.
- Times in the file are used as given, except the publication copy of a post (immutable, stamped at the import), the new public id of a widened entry and the moderation log.

## Day to day

```bash
systemctl status tabsira-api tabsira-vision tabsira-worker  # units
journalctl -u tabsira-api -f                       # API logs
pm2 status; pm2 logs tabsira-web                   # web
systemctl list-timers 'tabsira-*'                  # the scheduled work
sudo deploy/apply-config.sh --check                # does the host match the clone?
```

Log rotation (`/etc/logrotate.d/tabsira`) covers `/var/log/tabsira`; nginx rotates its own logs; the journal follows `journald.conf`.

## Cost, alternatives and content review

**What a scan costs.** Measured by `make eval` on the fifteen gold scenes with the real providers and recorded in [docs/EVALUATION.md](EVALUATION.md): $0.0204 a scan with the small-model reranker, and about $0.016 a scan after task 05.3 (run 3, «Runs of task 05.3»: $0.246 for the fifteen scenes with `RERANKER=off`, the default since decision 50), at about 18 s at p50 and 22 s at p95. A chat answer costs about $0.0012 (the twelve cases, $0.014). The admin area shows the running figures (AI cost and latency, decision 14); `AI_*__PRICES` holds the prices the numbers are computed from, so a price change is one setting, not a code change.

**Alternatives to each dependency.**

- The AI provider is one setting, `AI_PROVIDER=openai | ovh`, and every stage has its own model setting under `AI_OPENAI__*` and `AI_OVH__*`; switching provider switches the vision, planner, verifier, composer, embedding and chat models together (decisions 33 and 46). [docs/BENCHMARK.md](BENCHMARK.md) compares them on the same scenes: OpenAI `gpt-5.4-mini` is the default on quality (0.98), zero violations and speed (vision p95 5.7 s against 27 s), OVH `Qwen3.8-27B` is the measured fallback (quality 0.97, $0.0045 against $0.0033 a scan for the vision stage). `make benchmark` re-measures when a model or price changes. gpt-oss models are never used (AGENTS.md).
- The reranker is `RERANKER=off | llm | cross_encoder` (decision 50): off by default, the small model when the owners want it back, the cross-encoder in `services/vision` when no second model may be called.
- The detector is `services/vision` (Ultralytics YOLOE / YOLO-World) at `DETECTOR_URL`; a scan goes on without boxes when the service is down, since the vision model describes the scene on its own, so the detector can be replaced or dropped without stopping scans.
- Error tracking is optional (`GLITCHTIP_DSN` empty means off, decision 24); analytics are off unless `GA_MEASUREMENT_ID` and consent are both present (decision 28).
- The scripture store depends on nothing live: quranpedia's dumps and the hadith files are imported with their hashes checked, and the daily sync only applies quranpedia's corrections ([docs/SOURCES-AND-LICENSES.md](SOURCES-AND-LICENSES.md)).

**Who reviews content.**

- _Scripture_ is never written or edited by anyone in the app: the admin shows Quran and hadith records read-only (decision 14), and tests compare displayed text with its stored hash.
- _Hadith grades_ come from dorar.net only and are recorded by the owners' editors (decisions 18 and 47): an editor opens dorar in a browser and records the ruling in the admin rulings queue (`/admin/rulings-queue`, ordered by demand) or with `python -m src.cli.record_ruling`, starting with the rain-scene hadiths Bukhari 1032 and 2320. Until a hadith has a ruling, its insight shows the verse alone, unless the hadith counts as one of the enriched Sunnah file's (decision 58). [docs/ADMIN.md](ADMIN.md) describes the queue.
- _Posts, comments and map entries_ go through the automatic text guard first; what it holds, and what enough readers report, waits in the admin moderation queue (`/admin/moderation-queue`, decision 14) for a person to publish, refuse or remove it. Every decision is written to the moderation log and the audit log.
- _Ontology candidates_ (labels the detector saw that the world ontology does not know) are reviewed in the admin with the reviewer recorded.
- _Insights_ themselves are not edited by a moderator: an insight is published or withdrawn by its owner, and a published one can be reported like a post.

## What the owners must supply

Listed on the owners' board; none of it is in git.

- The application host and the data host (addresses, ssh access), and each one's Netbird address: `DEPLOY_HOST`, `DEPLOY_USER`, `APP_HOST_VPN_IP`, `DATA_HOST_VPN_IP`.
- DNS for `tabsira.me`, `www` and `api` pointing at the app host; the Netbird split-DNS entry for `admin.tabsira.me`.
- An email address for certbot. (A DNS provider's certbot plugin and a zone credential only if the admin certificate is issued by DNS-01.)
- The Jenkins credential `DEPLOY_SSH_KEY` (an ssh key whose public half is on the app user) and `DEPLOY_HOST_KEY` (the host's public key line, checked once).
- Every secret of `deploy/env.production.example`: database and Redis passwords (printed by the data host scripts), `HASH_SECRET` (generated), `ADMIN_TOTP_ENCRYPTION_KEY`, the S3 keys, the AI keys, SMTP, Google sign-in, `GLITCHTIP_DSN` (optional), `GA_MEASUREMENT_ID` and `CLARITY_PROJECT_ID` (optional).
- Where the dumps are copied off the data host, if anywhere.

`ADMIN_REQUIRE_TWO_FACTOR` is `false` in the template by the owners' decision: an admin who has not enrolled the second factor is not forced to.

## Rehearsal

On 2026-10-04 the deployment was rehearsed following this document, on two systemd containers on one machine standing in for the two hosts (Ubuntu 24.04, a private network standing in for the VPN, a second network for the public address): provisioning of both, a first deploy and a second one, a rollback, a deploy with `PRE_DEPLOY_BACKUP=true`, a backup, a restore beside the live database and over it, and `make smoke` against the app host. Every gap it showed is fixed above or in `deploy/`.

What a container rehearsal cannot show, and a run on two real servers still has to:

- Netbird itself: the interface `wt0`, split DNS for `admin.tabsira.me`, the subnet `100.64.0.0/10`. The scripts were given the containers' own interface and addresses (`VPN_IFACE`, `DATA_HOST_VPN_IP`, `APP_HOST_VPN_IP`).
- DNS and certbot: no certificate was issued; both host names were served with self-signed certificates (`--skip-tls`), and `provision-app.sh --dry-run` was the only run of the certbot step.
- A real firewall: the `ufw` rules were written and listed, but `ufw` was not enabled, so nothing was blocked.
- A real S3 bucket: the API's start-up refusal was seen (a missing bucket halts the master, with the bucket and endpoint named), and the deploy passed with a local S3-compatible stand-in; no real bucket, key or endpoint was tried.
- The detector: the deploy ran with `SKIP_VISION=true`, so its environment, the weights download and its restart were not exercised, and IndexNow was skipped (`SKIP_INDEXNOW=true`), because it would contact the search engines.
- The data imports (`scripts/data.sh`): not run. The deploy migrated an empty database, so the restore was checked on the schema and on a marker row, and `make smoke` fails its one check that needs scripture rows (`/scripture/quran/1/1`, 404).
- Restore time and dump size at real data volumes, memory and disk of real hosts, and a reboot of real machines (when the containers were restarted every unit came back, `pm2` included; the API halted until the stand-in's bucket, which it keeps in memory, was created again, as designed).

The package names and repositories (TimescaleDB, pgvector, redis.io) installed as written. The remaining vendor behaviour (Netbird, certbot's DNS plugin flags) is written from the vendors' documentation.
