# Operations

How TABSIRA runs in production, and how to deploy, roll back and provision it. Ported from the reference project's `docs/DEPLOYMENT.md` and deploy scripts. No Docker in production (decision 20): systemd, gunicorn, pm2, nginx.

Everything below lives in `deploy/` and `nginx/production/`. No real host, address, key or password is in git; the owners supply them (see [What the owners must supply](#what-the-owners-must-supply)). Production files never contain the development domain.

## Topology

```text
Internet ──► app host (public)                         data host (no public service)
             nginx :443  tabsira.me, api.tabsira.me      PostgreSQL 18  :5432 ┐ wt0 + loopback only,
             pm2  web   127.0.0.1:3000                   Redis          :6379 ┘ app host's VPN address only
             gunicorn   127.0.0.1:8000  ── Netbird VPN (wt0) ──►
             vision     127.0.0.1:8100
             timers     sync-quran, audit-retention
Admins ──► Netbird DNS ──► app host VPN address :443  admin.tabsira.me (VPN only)
```

| Piece                      | Where                                         | Run by                                |
| -------------------------- | --------------------------------------------- | ------------------------------------- |
| web (`apps/web`)           | `current/web`, pm2 app `tabsira-web`, cluster | pm2, started at boot by `pm2-<user>`  |
| API (`apps/api`)           | `current/apps/api`, `tabsira-api.service`     | systemd, gunicorn and uvicorn workers |
| vision (`services/vision`) | `current/services/vision`, `tabsira-vision`   | systemd, one worker, `127.0.0.1:8100` |
| daily Quran sync           | `tabsira-sync-quran.timer`                    | systemd, 02:30 UTC, one process       |
| audit retention policy     | `tabsira-audit-retention.timer`               | systemd, 03:40 UTC, one process       |
| database dumps             | `tabsira-pg-backup.timer` on the data host    | systemd, 03:15 UTC                    |
| IndexNow                   | last step of `deploy.sh`, production only     | the deploy, never a timer             |
| error tracking             | GlitchTip, only when `GLITCHTIP_DSN` is set   | the API (decision 24)                 |

Scheduled work runs in exactly one process: timers on the one application host, never a thread in each worker.

## Layout on the application host

```text
/srv/tabsira/repo               git clone every release is cut from
/srv/tabsira/releases/<id>      one folder per deploy (UTC time and short commit), never edited
/srv/tabsira/current            symlink to the live release
/srv/tabsira/previous           symlink to the release before it
/srv/tabsira/shared/.env        production environment (0600, owned by the app user)
/srv/tabsira/shared/{state,cache,vision-weights}
/srv/tabsira/static/_next/static  every recent build's static files, served by nginx
/var/log/tabsira                web logs (pm2); the API and timers log to the journal
```

A release holds the sources, the API's and vision's virtual environments, and `web/`, the assembled standalone build.

## Provisioning

Order matters: the data host first, because the first deploy migrates the database.

1. **Netbird** on both hosts (interface `wt0`). Note each host's VPN address.
2. **Data host** (as root, from a checkout):

   ```bash
   APP_HOST_VPN_IP=<app host VPN address> deploy/provision-data.sh --dry-run
   APP_HOST_VPN_IP=<app host VPN address> deploy/provision-data.sh
   ```

   It installs PostgreSQL 18 with PostGIS, pgvector and TimescaleDB, creates the role `tabsira` and the database `tabsira` with `search_path = app, geodata, public` and the nine extensions (`postgis`, `vector`, `timescaledb`, `pg_trgm`, `unaccent`, `pgcrypto`, `btree_gin`, `btree_gist`, `pg_stat_statements`), and installs Redis 8 with a password and protected mode. Both listen on `127.0.0.1` and the `wt0` address only (`DATA_HOST_VPN_IP` to name it). `pg_hba.conf` has one managed block: the application role from `APP_HOST_VPN_IP/32` with `scram-sha-256`, no ranges, no trust. The firewall step adds `ufw` rules that allow 5432 and 6379 from the app host on `wt0` and deny them elsewhere; it does not enable `ufw` (a wrong default over ssh locks you out) unless `FIREWALL_ENABLE=true`. Passwords are generated into `/etc/tabsira/postgres.env` and `/etc/tabsira/redis.env` (root only); the script ends by printing the URLs, with the password left as a placeholder, to paste into the application host's `.env`.

3. **Application host** (as root, from a checkout):

   ```bash
   APP_HOST_VPN_IP=<this host's VPN address> CERTBOT_EMAIL=<address> \
     CERTBOT_DNS_PLUGIN=<dns provider plugin> CERTBOT_DNS_CREDENTIALS=<credentials file> \
     APP_REPO=<git url> deploy/provision-app.sh --dry-run
   ```

   Run it without `--dry-run` once the plan reads right. It creates the user and layout, installs Node 24 (latest 24.x from nodejs.org, checksum verified), pnpm through corepack, pm2 (started at boot), uv and the Python 3.12 of `apps/api/.python-version`, nginx, certbot, the narrow sudoers file and `/usr/local/bin/tabsira-deploy`, and applies `deploy/apply-config.sh`. It writes `/srv/tabsira/shared/.env` from `deploy/env.production.example` when none exists and generates `HASH_SECRET`; every other `CHANGE_ME` is left for the owners.

4. Fill `/srv/tabsira/shared/.env`, then `tabsira-deploy --dry-run` and `tabsira-deploy` as the app user.
5. After the first deploy, as the app user: `make data`-style imports are run from the release (`cd /srv/tabsira/current && bash scripts/data.sh`), and `uv run python -m src.cli.make_admin` creates the first admin (`docs/ADMIN.md`).

## Deploying

```bash
tabsira-deploy --dry-run            # print every step with its values, run nothing
tabsira-deploy                      # deploy origin/main
tabsira-deploy --ref v1.2.0         # a tag, branch or commit
tabsira-deploy --rollback           # back to the previous release, no rebuild
```

`tabsira-deploy` fetches the clone, checks out the commit, and runs that commit's `deploy/deploy.sh`. The steps:

1. Take the lock; check the host and that `.env` says `ENVIRONMENT=production` and names no development address.
2. Optional dump (`PRE_DEPLOY_BACKUP=true`).
3. Cut `releases/<id>` with `git archive`, `uv sync --frozen --no-dev` for the API and vision, `pnpm install --frozen-lockfile`, build the web app (`NEXT_PUBLIC_*` are baked here from `.env`; the build refuses a development address), assemble `web/` and copy its static files to the shared static folder.
4. `check_config --live`, then the migrations: the `geodata` chain, then the `app` chain (`scripts/migrate.sh`), then the audit policy.
5. Pre-flight: boot the new API and the new web build on spare ports (18000, 3100) and wait until they answer. A release that cannot start is removed and the live one was never touched.
6. Switch `current` with one atomic rename.
7. Roll the API, then the web, then restart vision when `services/vision` changed.
8. Health gate; compare the host's nginx and units with the release (a warning); IndexNow (`node scripts/indexnow.mjs`, production only, never fails the deploy); prune old releases (five kept).

On a failure after the switch `current` goes back to the previous release and the API and web are rolled again. **Migrations are not reverted**: write migrations that the previous release can run against (add before you remove), and restore a dump (`deploy/restore-db.sh`) only as a last resort.

### The API roll (gunicorn)

`deploy/api-roll.sh`, ported from the reference project's `api-rolling-reload.sh`. The unit starts gunicorn through the `current` link (its python, its `--chdir`), so a worker forked after the link moves imports the new release. For each running worker: `TTIN` adds one, the script waits until it has stayed up for eight seconds and `/health/ready` answers, checks that the new worker really loaded files of the new release (from `/proc/<pid>/maps`; a worker that kept the old code stops the roll), then `TTOU` retires the oldest, which finishes its requests within `--graceful-timeout` (30 s). At least N workers serve at every moment. Afterwards the pool is brought to `API_WORKERS`.

A first start, or a changed Python, is a `systemctl restart tabsira-api` (workers keep the master's interpreter). The master keeps its start release alive on disk; the prune never deletes it and the deploy tells you when to restart the unit in a quiet hour.

### The web roll (pm2)

`deploy/web-roll.sh`, ported from `web-rolling-deploy.sh`. `deploy/ecosystem.config.cjs` runs `current/web/apps/web/server.js` in cluster mode (`WEB_INSTANCES`, default 2). `pm2 reload` runs one instance at a time; each must be online, up for five seconds and answer before the next is touched. The shared static folder keeps the files of older builds for seven days, because a tab opened before a deploy still asks for the old chunk names.

## nginx and TLS

`nginx/production/tabsira.me.conf` and `nginx/production/snippets/` are installed by `sudo deploy/apply-config.sh` (also `--check` and `--dry-run`). It builds every file aside, installs them, runs `nginx -t`, and **restores the previous files and does not reload when the test fails**. The deploy user cannot write `/etc`, so `deploy.sh` only warns when the host differs.

- Security headers live in snippets that every location that sets a header includes (a location that uses `add_header` drops the server block's headers). HSTS, a CSP for the web host that allows only the map tiles, Google Analytics 4 and Microsoft Clarity (injected after consent), `client_max_body_size 16m` for photos.
- `limit_req` on the open POST routes (`/auth/login`, `/auth/signup`, `/support`, `/consent`, `/client-errors`). nginx caches and serves no photo; public photos from the bucket or a CDN carry `Cache-Control: public, max-age=300`, never longer.
- The API trusts proxy headers from `127.0.0.1` only (`forwarded_allow_ips` in `deploy/gunicorn.conf.py`, handed to uvicorn), so the rate limit and the audit log see the visitor's address.
- No OCSP stapling: Let's Encrypt no longer issues OCSP responders.
- `tabsira.me`, `www` and `api`: certbot, HTTP challenge, webroot `/var/www/certbot`, renewal by `certbot.timer`, with a deploy hook that runs `nginx -t` before it reloads.

### The admin host

The admin area is served only at `https://admin.tabsira.me`, over the VPN.

- A separate server block listens on the app host's VPN address only (`APP_HOST_VPN_IP`, generated into `tabsira-admin-listen.conf`) with `allow <VPN subnet>; deny all;` as a second guard (`VPN_SUBNET`, default `100.64.0.0/10`, Netbird's own range). It proxies `/admin` to the API with `Host: admin.tabsira.me`, redirects `/` to `/admin/`, sets `no-store` and `frame-ancestors 'none'` (`docs/ADMIN.md`), and rate limits `/admin/login` to thirty requests a minute per address.
- `api.tabsira.me` answers 404 for `/admin` and everything under it. The API also refuses `/admin` on any host but `ADMIN_URL`.
- **DNS.** No public record exists for `admin.tabsira.me`. In the Netbird dashboard add a DNS nameserver entry (split DNS) for the domain `admin.tabsira.me`, or a custom zone with an A record, that resolves it to the app host's VPN address, and distribute it to the admins' peer group.
- **TLS.** The host is not reachable from the internet, so its certificate is issued by a DNS-01 challenge: `certbot certonly --dns-<plugin> --dns-<plugin>-credentials <file> -d admin.tabsira.me`, run by `deploy/provision-app.sh`. The owners supply the DNS provider's certbot plugin name (`CERTBOT_DNS_PLUGIN`) and an API credential for the zone (`CERTBOT_DNS_CREDENTIALS`, a file mode 0600 that never goes in git). Renewal is automatic with the same credential.
- Locally, `admin.tabsira.test` is added by `scripts/setup-nginx-local.sh` (mkcert certificate, `/etc/hosts` line) and answers this machine only.

## Backups

On the data host `tabsira-pg-backup.timer` runs nightly at 03:15 UTC (`/usr/local/bin/tabsira-pg-backup`): a custom-format dump of `tabsira` into `/var/backups/tabsira`, verified with `pg_restore --list`, plus a globals file (roles and their `search_path`). Dumps older than 14 days are deleted, but the newest three are always kept (`BACKUP_KEEP_DAYS`, `BACKUP_KEEP_MIN`). Run one now: `systemctl start tabsira-pg-backup.service`. `deploy/backup-db.sh --url <url>` takes one from the app host before a risky deploy (`PRE_DEPLOY_BACKUP=true`).

These are local copies: they do not survive the loss of the data host. Copying `/var/backups/tabsira` off the machine is the owners' decision (listed below).

Restore: `deploy/restore-db.sh <dump>` restores into a new database (`tabsira_restore`) so the live one is never overwritten by accident; `--into tabsira --yes-overwrite` replaces it.

## Day to day

```bash
systemctl status tabsira-api tabsira-vision        # units
journalctl -u tabsira-api -f                       # API logs
pm2 status; pm2 logs tabsira-web                   # web
systemctl list-timers 'tabsira-*'                  # the scheduled work
sudo deploy/apply-config.sh --check                # does the host match the release?
```

Log rotation (`/etc/logrotate.d/tabsira`) covers `/var/log/tabsira`; nginx rotates its own logs; the journal follows `journald.conf`.

## What the owners must supply

Listed on the owners' board; none of it is in git.

- The application host and the data host (addresses, ssh access), and each one's Netbird address: `DEPLOY_HOST`, `DEPLOY_USER`, `APP_HOST_VPN_IP`, `DATA_HOST_VPN_IP`.
- DNS for `tabsira.me`, `www` and `api` pointing at the app host; the Netbird split-DNS entry for `admin.tabsira.me`.
- The DNS provider's certbot plugin and a zone API credential for the admin certificate; an email address for certbot.
- The Jenkins credential `DEPLOY_SSH_KEY` (an ssh key whose public half is on the app user) and `DEPLOY_HOST_KEY` (the host's public key line, checked once).
- Every secret of `deploy/env.production.example`: database and Redis passwords (printed by the data host scripts), `HASH_SECRET` (generated), `ADMIN_TOTP_ENCRYPTION_KEY`, the S3 keys, the AI keys, SMTP, Google sign-in, `GLITCHTIP_DSN` (optional), `GA_MEASUREMENT_ID` and `CLARITY_PROJECT_ID` (optional).
- Where the dumps are copied off the data host, if anywhere.

`ADMIN_REQUIRE_TWO_FACTOR` is `false` in the template by the owners' decision: an admin who has not enrolled the second factor is not forced to.

## Not verified

Nothing here was run against a server. The scripts pass `shellcheck` and `shfmt`, every one has a `--dry-run` that was run, and the nginx file passes `nginx -t` with stand-in certificates. The package names and repositories (TimescaleDB, pgvector, redis.io), the Netbird behaviour and certbot's DNS plugin flags are written from the vendors' documentation and need a first run on a scratch machine.
