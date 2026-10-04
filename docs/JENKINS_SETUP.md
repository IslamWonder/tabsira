# Jenkins

How the continuous integration of TABSIRA is set up: what a build does, which plugins and credentials Jenkins needs, how a push on the Gitea server starts a build, and every environment variable and where it comes from. The files behind it are the root `Jenkinsfile`, [`jenkins/`](../jenkins/README.md) and `sonar-project.properties`.

Nothing in the repository names a Jenkins, Gitea or SonarQube server. The owners fill in the three addresses (see [What the owners fill in](#what-the-owners-fill-in)).

## The shape of a build

```text
Checkout -> Prepare -> Services -> Install -> Migrations
  -> in parallel: API tests | Vision tests | Web build, accessibility and tests | Lint | Security gate | Audit
  -> SonarQube (main, or RUN_SONAR) -> archive -> notify -> remove the services
```

| Stage               | Script                                                             | Gates the build?                                                                        |
| ------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Prepare             | `jenkins/prepare-jenkins-deps.sh --check`                          | Yes: a missing tool fails in seconds                                                    |
| Services            | `jenkins/ci-services.sh up`                                        | Yes: PostgreSQL and Redis                                                               |
| Install             | `uv sync --locked` (api, vision), `pnpm install --frozen-lockfile` | Yes                                                                                     |
| Migrations          | `scripts/migrate.sh`                                               | Yes: the `geodata` chain, then the `app` chain                                          |
| API tests           | `scripts/test-coverage.sh`                                         | Yes: 100 % of the suite and of the changed lines                                        |
| Vision tests        | `jenkins/vision-coverage.sh`                                       | Yes: 100 % (`fail_under` in its `pyproject.toml`)                                       |
| Web build and tests | `pnpm build`, `scripts/test-web-coverage.sh`                       | Yes; skipped with a notice while `apps/web` does not exist                              |
| Web accessibility   | `jenkins/web-a11y.sh`                                              | Yes: any axe violation; needs Chromium, `RUN_A11Y` turns it off                         |
| Lint                | `scripts/lint.sh`                                                  | Yes: format check, lint rules, types, shell, Markdown                                   |
| Security gate       | `scripts/security-gate.sh`                                         | Yes: secrets in the tree or the history, critical advisories in production dependencies |
| Audit               | `scripts/audit.sh`                                                 | No: findings make the build unstable                                                    |
| SonarQube           | `jenkins/sonar-scan.sh`                                            | No: a failed gate or an unreachable server makes the build unstable                     |

The branches after Migrations share nothing but the checkout, so they run side by side with `failFast`: the build costs its longest branch, and a red suite stops the others. Red stays reserved for broken code and tests; the advisory audit and SonarQube can only make a build yellow.

### The accessibility stage

`Web Accessibility` runs `jenkins/web-a11y.sh` in the web branch, after the SEO checks and on the same production build. It starts a tiny stub API (`apps/web/scripts/lib/api-stub.mjs`, loopback port 8010) that answers the web server and the check with the sample answers of the screenshots, starts `next start` on port 3188, and drives Chromium through the DevTools protocol with axe-core (WCAG 2.2 AA) on the scene, the cookie screen, sign-in and «ملفي», in both themes at 375 and 1440 px. It sets `A11Y_FAIL_ON=any`: any violation, whatever its impact, fails the stage and the build. Nothing comes from a database or a real API, and axe-core is a pinned dev dependency, so nothing is fetched.

What the agent needs, beyond the rest of this file:

- A Chromium or Chrome the agent user can run: `chromium` or `google-chrome` on the `PATH`, or `CHROME_PATH` set (in `jenkins/jenkins.env`, on the job or globally), or Playwright's headless shell in the agent user's `~/.cache/ms-playwright` (`pnpm dlx playwright install chromium-headless-shell`). The pipeline does not install it, because a build cannot add system packages.
- A browser started as root or inside a container without user namespaces needs `CHROME_NO_SANDBOX=1`.
- Free loopback ports 3188 (web), 8010 (stub) and 9333 (DevTools; `A11Y_WEB_PORT`, `A11Y_API_PORT`, `CHROME_DEBUG_PORT` change them). Two builds on one agent at the same time would collide on them: keep one executor, or give each build its own ports.

The agent's Chromium cannot be assumed, so the stage sits behind the build parameter `RUN_A11Y`, which defaults to ticked. On an agent without a browser, untick it on the job (or set a default there): the build then shows a warning badge, never a silent pass. Run it by hand with `bash jenkins/web-a11y.sh` after `pnpm build`; `--dry-run` prints the plan.

### The per-build services

Each build starts its own PostgreSQL 18 and its own Redis as containers (`jenkins/ci-services.sh up`), on loopback ports the kernel picks and with passwords generated for that build, and removes them at the end (`down`, and a `sweep` of leftovers older than `CI_SWEEP_MAX_AGE`). Nothing is shared between builds, so there is no database or Redis secret to store and no collision to prevent.

The image is `timescale/timescaledb-ha`, pinned in `jenkins/jenkins.env` as `CI_PG_IMAGE` (tag `pg18.6-ts2.30.2`). It is the one image that bundles PostgreSQL 18, PostGIS, pgvector and the TimescaleDB Community build; the Community build is the one that has retention and compression policies (decision 13). The container is started with `pg_stat_statements` preloaded next to `timescaledb`, TimescaleDB's telemetry off, and `fsync` off because the data is deleted with the container.

`jenkins/ci-postgres/*.sql` is the SQL form of `scripts/setup-db.sh`: the role `tabsira` (not a superuser, `CREATEDB`, `search_path` `app, corpus, geodata, vectors, public`), the databases `tabsira`, `tabsira_test` and `tabsira_template`, the schemas `app`, `corpus`, `geodata` and `vectors`, and the nine extensions (decision 15). Redis (decision 21: the job queue, scan-progress pub/sub, caches and rate-limit counters) is `redis:8.10.2-alpine`, pinned as `CI_REDIS_IMAGE`, with `--requirepass` as production has it and no persistence. `REDIS_URL` points at database 0 and `TEST_REDIS_URL` at database 1, the way `TEST_DATABASE_URL` is a separate `_test` database. There is no GlitchTip, PostHog or other telemetry in a build: `GLITCHTIP_DSN` is forced empty and the Turborepo and Next.js telemetry are off.

`up` then checks as the application role, over TCP, that it connects with the right `search_path` and can copy the template, which every pytest-xdist worker does. An image that lacks an extension fails there, with the names, instead of in a migration.

### Coverage

The suites write Cobertura XML and JUnit XML next to their HTML reports: `apps/api/coverage/`, `services/vision/coverage/` and `apps/web/coverage/` (`lcov.info` for SonarQube, `cobertura-coverage.xml` for Jenkins). The pipeline hands them to the `junit`, `publishHTML` and `recordCoverage` steps. The last two come from optional plugins: without them the step logs one line and the build carries on. The gates themselves do not depend on a plugin.

## SonarQube

On the branch named by `SONAR_BRANCH` (default `main`), and on any build where `RUN_SONAR` is ticked, the `SonarQube` stage runs `jenkins/sonar-scan.sh` against `SONAR_HOST_URL`. It reads the coverage the suites have just written:

| Language       | Report                                                                            |
| -------------- | --------------------------------------------------------------------------------- |
| Python, API    | `apps/api/coverage/coverage.xml`                                                  |
| Python, vision | `services/vision/coverage/coverage.xml`                                           |
| TypeScript     | `apps/web/coverage/lcov.info` (the JavaScript analyzer reads lcov, not Cobertura) |

What is analysed is `sonar-project.properties`. `sonar-scan.sh` reads its `sonar.sources` and `sonar.tests` lines and drops a directory that does not exist yet (`apps/web` until the web app is built), which the scanner itself would refuse. The scanner is pinned (8.1.0.6389, the latest release on 4 October 2026), checked against the SHA-256 SonarSource publishes, cached in `~/.cache/sonar-scanner` and ships its own JRE, so the agent needs no Java. It waits for the quality gate. The token reaches it as the `SONAR_TOKEN` environment variable, never on a command line.

The Community Build keeps a single branch, which is why only `SONAR_BRANCH` is analysed by default: analysing another branch replaces what the server shows. The Jenkins SonarQube plugin is not used, so no server entry or scanner tool needs configuring in Jenkins.

On the SonarQube server: create the project with the key in `SONAR_PROJECT_KEY` (default `tabsira`), and a token allowed to run analyses on it. A project analysis token is enough.

## Deploy stage

Off by default. Tick `DEPLOY` on a build of `DEPLOY_BRANCH` (`main`): after the build the stage runs `deploy/remote-deploy.sh`, which connects over ssh to `DEPLOY_USER@DEPLOY_HOST` and runs `tabsira-deploy --ref <this commit>` there (`docs/OPERATIONS.md`). `DEPLOY_DRY_RUN` prints the steps on the host and changes nothing. An unstable build (advisory audit, Sonar gate) is deployed with a warning badge, because ticking `DEPLOY` is the approval; a failed build never reaches the stage.

| Name                       | Default          | Set in                 | Meaning                                                                 |
| -------------------------- | ---------------- | ---------------------- | ----------------------------------------------------------------------- |
| `DEPLOY_HOST`              | blank            | job, global, parameter | The application host. The stage fails when blank                        |
| `DEPLOY_USER`              | blank            | job, global, parameter | The application user on that host                                       |
| `DEPLOY_HOST_KEY`          | blank            | job, global            | The host's public ssh key line (`ssh-keyscan -t ed25519`), checked once |
| `DEPLOY_PORT`              | `22`             | file, job, global      | ssh port                                                                |
| `DEPLOY_CREDENTIALS_ID`    | `DEPLOY_SSH_KEY` | file, job, global      | Id of the "SSH Username with private key" credential                    |
| `DEPLOY_BRANCH`            | `main`           | file, job, global      | The only branch that may deploy                                         |
| `DEPLOY`, `DEPLOY_DRY_RUN` | `false`          | build parameters only  | Deploy this build; only print the steps                                 |

The key is a Jenkins credential, bound to a file for the one step; the host, user and host key are variables, never in the repository.

## Environment variables

Every setting has a default in [`jenkins/jenkins.env`](../jenkins/jenkins.env), which is committed and holds no secret. Precedence, highest first:

1. the **build parameter** of the same name, when it is not blank;
2. a **variable on the Jenkins job**, or in Manage Jenkins > System > Global properties > Environment variables, when it is not blank;
3. **`jenkins/jenkins.env`**.

| Name                          | Default                                    | Set in                       | Meaning                                                                                            |
| ----------------------------- | ------------------------------------------ | ---------------------------- | -------------------------------------------------------------------------------------------------- |
| `SONAR_HOST_URL`              | blank                                      | file, job, global, parameter | SonarQube address. Blank skips the stage with a warning; `RUN_SONAR` with it blank fails the stage |
| `SONAR_PROJECT_KEY`           | `tabsira`                                  | file, job, global, parameter | Project key on the server                                                                          |
| `SONAR_PROJECT_NAME`          | `TABSIRA`                                  | file, job, global            | Display name                                                                                       |
| `SONAR_CREDENTIALS_ID`        | `SONAR_TOKEN`                              | file, job, global, parameter | Id of the Jenkins secret-text credential that holds the token                                      |
| `SONAR_BRANCH`                | `main`                                     | file, job, global            | The branch analysed without asking                                                                 |
| `SONAR_QUALITYGATE_TIMEOUT`   | `600`                                      | file, job, global            | Seconds to wait for the quality gate                                                               |
| `NODE_TOOL_NAME`              | `node-24-lts`                              | file, job, global, parameter | Name of the NodeJS tool that provides Node 24                                                      |
| `CI_TIMEOUT_MINUTES`          | `60`                                       | file, job, global            | Minutes before a build is aborted                                                                  |
| `ZULIP_STREAM`, `ZULIP_TOPIC` | blank                                      | file, job, global, parameter | Where to post the result. Either one blank sends nothing                                           |
| `CI_REDIS_IMAGE`              | `redis:8.10.2-alpine`                      | file, job, global, parameter | The build's Redis image                                                                            |
| `CI_PG_IMAGE`                 | `timescale/timescaledb-ha:pg18.6-ts2.30.2` | file, job, global, parameter | The build's database image                                                                         |
| `CI_WAIT_SECONDS`             | `300`                                      | file, job, global            | Seconds to wait for each of the database and Redis                                                 |
| `CI_SWEEP_MAX_AGE`            | `4h`                                       | file, job, global            | Age after which a container is a leftover (`90m`, `4h`, `2d`)                                      |
| `CI_PYTEST_WORKERS`           | `0`                                        | file, job, global, parameter | Parallel pytest workers; 0 is serial. See the note below                                           |
| `RUN_SONAR`, `RUN_AUDIT`      | `false`, `true`                            | build parameters only        | Analyse a branch other than `SONAR_BRANCH`; run the advisory audit                                 |
| `RUN_A11Y`                    | `true`                                     | build parameter only         | Run the accessibility check; untick only on an agent without Chromium                              |
| `CHROME_PATH`                 | blank                                      | file, job, global            | Chromium or Chrome binary for the accessibility check; blank finds one                             |
| `CHROME_NO_SANDBOX`           | blank                                      | file, job, global            | `1` runs the browser with `--no-sandbox` (root or container)                                       |

Set by the pipeline for every build, never by hand:

| Name                                                                                                                                              | Value                                       | Why                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `CI`, `JENKINS_BUILD`                                                                                                                             | `true`                                      | The scripts skip the root `.env` and write `.ci_metrics/*.json`                                 |
| `ENVIRONMENT`                                                                                                                                     | `development`                               | The API's settings need a valid environment, and `.test` URLs are valid only outside production |
| `UV_PYTHON_PREFERENCE`                                                                                                                            | `only-managed`                              | uv builds the Python the projects name, never the agent's own `python3`                         |
| `BRANCH_NAME`                                                                                                                                     | the branch                                  | Set by a multibranch job; set by the pipeline otherwise. The diff-coverage gate reads it        |
| `NODE_HOME`                                                                                                                                       | the NodeJS tool                             | Put on `PATH` for every stage                                                                   |
| `DATABASE_URL`, `SYNC_DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `TEST_REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` | the per-build services, from `.env.ci`      | Generated per build; they die with the container                                                |
| `GLITCHTIP_DSN`                                                                                                                                   | empty                                       | Error tracking is off in a build, whatever a Jenkins global variable says (decision 24)         |
| `TURBO_TELEMETRY_DISABLED`, `NEXT_TELEMETRY_DISABLED`, `DO_NOT_TRACK`                                                                             | `1`                                         | No tool of the build reports usage to a third party                                             |
| `PYTEST_WORKERS`                                                                                                                                  | `CI_PYTEST_WORKERS`                         | Read by `scripts/test-coverage.sh`                                                              |
| `SONAR_TOKEN`                                                                                                                                     | the credential, in the SonarQube stage only | Read by the scanner, never printed                                                              |

`CI_PYTEST_WORKERS` stays `0` for now. With more workers the copy each of them makes of the test template fails (`source database ... is being accessed by other users`), because TimescaleDB's scheduler keeps a session in the template after `tests/conftest.py` closes it to connections. The test fixture has to end that session before workers can run in parallel; `jenkins/ci-services.sh` already does it for `tabsira_template`.

## Credentials

One credential, and one plugin-level secret.

| Id                                     | Type                 | Where                                    | Used by                                             |
| -------------------------------------- | -------------------- | ---------------------------------------- | --------------------------------------------------- |
| `SONAR_TOKEN` (`SONAR_CREDENTIALS_ID`) | Secret text          | Manage Jenkins > Credentials > Global    | `SonarQube` stage, the scanner only                 |
| a Gitea credential                     | token or SSH key     | on the Gitea server entry, or on the job | Scanning the repositories and cloning               |
| the Zulip bot                          | URL, e-mail, API key | Manage Jenkins > System > Zulip          | `zulipSend`, only when a stream and a topic are set |

Without the SonarQube token only the `SonarQube` stage suffers: it makes the build unstable. The database and Redis passwords are generated per build and are no credentials.

## Plugins

Needed:

| Plugin                 | Id                       | For                                                               |
| ---------------------- | ------------------------ | ----------------------------------------------------------------- |
| Pipeline               | `workflow-aggregator`    | The scripted pipeline                                             |
| Git                    | `git`                    | `checkout scm`                                                    |
| Credentials Binding    | `credentials-binding`    | `withCredentials`, the SonarQube token                            |
| Pipeline Utility Steps | `pipeline-utility-steps` | `readProperties` (`jenkins.env`, `.env.ci`), `readJSON` (metrics) |
| NodeJS                 | `nodejs`                 | The Node 24 tool (`NODE_TOOL_NAME`)                               |
| Timestamper            | `timestamper`            | Timestamps in the console                                         |
| Workspace Cleanup      | `ws-cleanup`             | `cleanWs`                                                         |
| JUnit                  | `junit`                  | Test results                                                      |
| Gitea                  | `gitea`                  | Discovering branches and starting a build from a push             |

Optional, each detected at run time and skipped with a log line when absent:

| Plugin         | Id              | Adds                                                      |
| -------------- | --------------- | --------------------------------------------------------- |
| Coverage       | `coverage`      | Trend graphs and a per-file view of the Cobertura reports |
| HTML Publisher | `htmlpublisher` | The HTML coverage reports in the sidebar                  |
| Badge          | `badge`         | Badges on the build page                                  |
| Zulip          | `zulip`         | The notification                                          |
| Gitea Checks   | `gitea-checks`  | Build status on the commit in Gitea                       |

## Setting Jenkins up

The commands and menus below follow the plugins' own documentation; they have not been run against the owners' Jenkins.

1. **Agent.** On the agent that builds, as an administrator:

   ```bash
   sudo bash jenkins/prepare-jenkins-deps.sh      # packages, PostgreSQL client 18, quality tools, uv
   sudo usermod -aG docker jenkins                # Docker engine must already be installed
   sudo systemctl restart jenkins                 # or the agent process: group membership is fixed when it starts
   sudo -u jenkins docker info >/dev/null && echo ok
   ```

   Docker is the one thing the script verifies and does not install. Only the build's database and Redis run in it.

2. **Node.** Manage Jenkins > Tools > NodeJS: add an installation named like `NODE_TOOL_NAME` (default `node-24-lts`), installing Node 24. Corepack, which comes with Node 24, provides the pnpm the root `package.json` pins.
3. **Plugins.** Install the needed ones above, and as many optional ones as you want.
4. **Credentials.** Add the SonarQube token as a Secret text credential, id `SONAR_TOKEN`, or another id and set `SONAR_CREDENTIALS_ID`.
5. **Gitea server.** Manage Jenkins > System > Gitea Servers: the server name, its address and a credential.
6. **The job.** New Item > Multibranch Pipeline (or Organization Folder, "Gitea Organization"), source Gitea, the repository, script path `Jenkinsfile`. Behaviours: discover branches, discover pull requests from the origin repository. **Do not add "shallow clone"**: the security gate scans the whole history and the diff-coverage gate compares with `origin/main`.
7. **Variables and parameters.** Fill in `SONAR_HOST_URL` in `jenkins/jenkins.env` (a commit), or on the job, or globally. Run the job once so Jenkins registers the build parameters.

### The Gitea webhook

With "Manage hooks" ticked on the Gitea server entry, the plugin creates the hooks itself. By hand, in Gitea: the repository (or the organization) > Settings > Webhooks > Add Webhook > Gitea:

| Field             | Value                                                                 |
| ----------------- | --------------------------------------------------------------------- |
| Target URL        | `<Jenkins address>/gitea-webhook/post`                                |
| HTTP method       | `POST`                                                                |
| POST content type | `application/json`                                                    |
| Trigger on        | Push events, Create and Delete events (branches), Pull request events |
| Active            | ticked                                                                |

Gitea must be able to reach Jenkins, and the agent must be able to reach Gitea over the protocol of the credential (HTTPS for a token, SSH for a key). If Jenkins is behind a firewall, the plugin's scan interval is the fallback.

## What the owners fill in

| What                         | Where it goes                                                |
| ---------------------------- | ------------------------------------------------------------ |
| Jenkins address              | Used by the webhook URL; nothing in the repository needs it  |
| Gitea address and credential | Jenkins: Gitea server entry and job                          |
| SonarQube address            | `SONAR_HOST_URL`                                             |
| SonarQube token              | The `SONAR_TOKEN` credential                                 |
| Zulip stream and topic       | `ZULIP_STREAM`, `ZULIP_TOPIC`, plus the Zulip bot in Jenkins |

## Housekeeping

Three layers, so a container never outlives its build for long:

1. the build's `finally` runs `ci-services.sh down`;
2. every build runs `ci-services.sh sweep` before it starts as well as after, because a build that dies before its teardown never cleans up after itself;
3. optionally, a timer on the agent runs the same sweep, so it happens when nothing is building:

   ```ini
   # /etc/systemd/system/tabsira-ci-sweep.service
   [Unit]
   Description=Sweep leftover TABSIRA CI containers

   [Service]
   Type=oneshot
   User=jenkins
   ExecStart=/bin/bash /path/to/a/checkout/jenkins/ci-services.sh sweep
   ```

   with an hourly `tabsira-ci-sweep.timer` beside it.

`sweep` goes by label (`tabsira.ci=1`) and by age, so a build that is running is never touched. It removes containers only: images are never pruned on a timer.

## Not part of this setup

- Deployment by default. The pipeline builds and tests. An optional `Deploy` stage (below) runs only when the `DEPLOY` parameter is ticked on `DEPLOY_BRANCH`; nothing deploys on its own.
- An end-to-end pipeline (a `Jenkinsfile.e2e`). There is no end-to-end suite yet.
