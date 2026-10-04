# Setting up a Windows machine natively

The Windows testing laptop runs TABSIRA on Windows itself: no Docker, no WSL, no Linux virtual machine. The PowerShell scripts in `scripts/windows/` are the counterparts of the shell scripts in `scripts/` and of the make targets, which stay the reference (the Linux and macOS machines, Jenkins and Docker use those). Each step is idempotent and starts with the check that says it is already done, like [docs/SETUP.md](SETUP.md), which this page follows.

Everything that is not part of the checkout goes beside it, in `..\tabsira-tools` (`TABSIRA_TOOLS` names another folder; avoid a path with spaces): PostgreSQL, nginx, downloads, build folders, the logs of the running services. Artifacts you make still go to `..\tabsira-artifact`.

## What you need first

- Windows 10 or 11 with winget (App Installer), Git for Windows (its bash runs the repository's shell scripts and git hooks), and an account that can elevate (UAC).
- The same things from the owners as on any machine: the two corpora, the GeoNames export, the scripture vectors, an OpenAI key. See the table in [docs/SETUP.md](SETUP.md).
- About 8 GB free where `..\tabsira-tools` lives, plus the Visual Studio C++ build tools on the system drive if pgvector is built (below).

Run the scripts from a normal PowerShell (not elevated) in the checkout:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once, if scripts are blocked
scripts\windows\provision-dev.ps1
```

## What `provision-dev.ps1` does

| Step            | Script                  | Runs as  | What it installs or writes                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------- | ----------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. System       | `provision-system.ps1`  | elevated | Node 24 LTS (`.nvmrc`; another Node from the same installer is replaced). PostgreSQL 18 as the service `postgresql-x64-18` under `..\tabsira-tools\PostgreSQL\18`, with PostGIS 3.6 (OSGeo bundle), TimescaleDB (Timescale's Windows zip) and pgvector; `shared_preload_libraries = timescaledb, pg_stat_statements`. Memurai Developer (Redis 7 compatible) as the service `Memurai` on 127.0.0.1:6379. The three `.test` names in the hosts file. |
| 2. Tools        | `install-tools.ps1`     | you      | uv, mkcert, the pnpm pinned in `package.json`, shfmt, shellcheck, gitleaks, jq (winget, user scope).                                                                                                                                                                                                                                                                                                                                                |
| 3. Database     | `setup-db.ps1`          | you      | Role `tabsira`, databases `tabsira`, `tabsira_test`, `tabsira_template`, the three schemas and every extension; `DATABASE_URL`, `SYNC_DATABASE_URL`, `TEST_DATABASE_URL` in `.env` (created from `.env.example`).                                                                                                                                                                                                                                   |
| 4. HTTPS        | `setup-nginx-local.ps1` | you      | mkcert authority (Windows asks once to trust it), a certificate for the three names, nginx for Windows in `..\tabsira-tools\nginx` with the repository's `nginx/local/tabsira.test.conf` translated for this machine.                                                                                                                                                                                                                               |
| 5. Dependencies | `install.ps1`           | you      | `pnpm install`, `uv sync` in `apps/api` and `services/vision`, the git hooks. `-SkipVision` leaves out the detector's torch (about 1 GB).                                                                                                                                                                                                                                                                                                           |

The elevated step opens its own window and writes everything to `..\tabsira-tools\logs\provision-system.log`. The PostgreSQL superuser password is generated once and written to `%APPDATA%\postgresql\pgpass.conf`, where psql and the scripts read it; it is never printed. An existing PostgreSQL 18 is used as it is, and then its password must already be in that file.

**pgvector.** pgvector publishes no Windows binary, so the script builds it from the official source release with the Visual Studio 2022 C++ build tools, the way its README describes, installing the build tools through winget when they are missing (about 15 minutes, a few GB on the system drive). `-PgvectorZip <zip>` installs a build you trust instead; `-SkipPgvector` leaves pgvector out, and then the vectors chain does not migrate.

Switches: `-SkipSystem` (the elevated part is done), `-SkipInstall`, `-SkipVision`, `-SkipNode` (keep the Node that is installed), `-PgvectorZip`, `-SkipPgvector`.

## Then, like any machine

```powershell
scripts\windows\migrate.ps1      # geodata chain, then app chain, then vectors chain
scripts\windows\dev.ps1          # nginx + api + worker + web (+ vision), Ctrl-C stops all
```

Steps 4 to 7 of [docs/SETUP.md](SETUP.md) (corpora, scripture store, GeoNames, vectors) are the same here; run their shell scripts from Git bash (`bash scripts/data.sh`), or the `uv run python -m src.cli...` commands they wrap from PowerShell in `apps\api`. `psql` and `pg_restore` are in `..\tabsira-tools\PostgreSQL\18\bin`.

`dev.ps1` starts nginx when it is not running and stops it at the end; every service's output is prefixed with its name and kept in `..\tabsira-tools\logs\<name>.log`. `-NoVision`, `-NoWorker` and `-NoNginx` leave a service out. Then open `https://tabsira.test` (API: `https://api.tabsira.test`, admin: `https://admin.tabsira.test`). Chrome, Edge and curl trust the certificate through the Windows store; Firefox imports `rootCA.pem` from the checkout.

## Day to day

| On Linux and macOS | On Windows                                                             |
| ------------------ | ---------------------------------------------------------------------- |
| `make install`     | `scripts\windows\install.ps1`                                          |
| `make migrate`     | `scripts\windows\migrate.ps1`                                          |
| `make dev`         | `scripts\windows\dev.ps1`                                              |
| `make test`        | `pnpm test` and, in `apps\api`, `uv run pytest -n 2`                   |
| `make lint`        | `pnpm lint` and, in `apps\api`, `uv run ruff check . && uv run mypy .` |
| `make format`      | `bash scripts/format.sh` from Git bash                                 |

The other targets (`data`, `coverage`, `eval`, `smoke`, `benchmark`, `stats`) are shell scripts that run from Git bash once uv and pnpm are on the PATH; they have no PowerShell counterpart yet.

## Where things are

| What                    | Where                                                          |
| ----------------------- | -------------------------------------------------------------- |
| PostgreSQL              | `..\tabsira-tools\PostgreSQL\18` (service `postgresql-x64-18`) |
| Superuser password      | `%APPDATA%\postgresql\pgpass.conf`                             |
| Redis-compatible server | `C:\Program Files\Memurai` (service `Memurai`)                 |
| nginx and its config    | `..\tabsira-tools\nginx` (`conf\tabsira.conf`)                 |
| Certificates            | `nginx\local\certs` in the checkout, copied to nginx           |
| Service logs            | `..\tabsira-tools\logs`                                        |
| Downloads and builds    | `..\tabsira-tools\downloads`, `..\tabsira-tools\build`         |
