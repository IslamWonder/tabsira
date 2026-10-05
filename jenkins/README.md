# Jenkins

The scripts and defaults behind the root `Jenkinsfile`. How to set Jenkins up, with the plugin list, the credentials, the Gitea webhook and every environment variable, is in [docs/JENKINS_SETUP.md](../docs/JENKINS_SETUP.md).

> **No secret lives in this repository.** The addresses and names the pipeline uses are in [`jenkins.env`](jenkins.env), which holds no secret and is meant to be edited in git. The one secret, the SonarQube token, is a Jenkins credential.

## Files

| File                      | Purpose                                                                                              | Used by                        |
| ------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------ |
| `jenkins.env`             | Defaults of every setting: SonarQube, Node tool, Zulip, service images, timeouts                     | `Jenkinsfile`, every script    |
| `ci-env.sh`               | Loads `jenkins.env` for a script without overriding a value that is already set                      | sourced by the scripts         |
| `ci-services.sh`          | Starts, removes and sweeps the build's PostgreSQL and Redis containers                               | `Services` stage and `finally` |
| `ci-postgres/*.sql`       | The role, databases, schemas and nine extensions of that database                                    | `ci-services.sh up`            |
| `vision-coverage.sh`      | The vision service's tests with coverage, reports in `services/vision/coverage/`                     | `Vision Tests` stage           |
| `sonar-scan.sh`           | Pinned, checksum-verified SonarScanner run on the coverage the suites wrote, gate waited on          | `SonarQube` stage              |
| `prepare-jenkins-deps.sh` | One-time agent setup (`sudo`), or `--check` to verify it                                             | `Prepare` stage, the operator  |
| `Jenkinsfile.deploy`      | The production deploy job: ssh to the application host, `git pull`, `deploy/deploy.sh`, health check | `tabsira-deploy`, held inline  |
| `tabsira-deploy.xml.tmpl` | That job's configuration with its parameters; `@SCRIPT@` receives the Jenkinsfile                    | `apply-jobs.sh`                |
| `apply-jobs.sh`           | Creates or updates the jobs Jenkins does not discover by itself; run after each change               | the operator                   |

The scanner's scope is [`../sonar-project.properties`](../sonar-project.properties).

## What a build does

```text
Checkout -> Prepare -> Services -> Install -> Migrations
  -> in parallel: API tests | Vision tests | Web build, accessibility and tests | Lint | Security gate | Audit
  -> SonarQube (main, or RUN_SONAR) -> archive -> notify -> remove the services
```

- **Services.** Each build starts its own PostgreSQL 18 with PostGIS, pgvector and TimescaleDB (image `CI_PG_IMAGE`) and its own Redis (image `CI_REDIS_IMAGE`, with a password), on loopback ports the kernel picks and with passwords generated for that build. Nothing is shared, so builds cannot collide and there is no secret to store. `ci-services.sh up` writes the addresses to `.env.ci` (`DATABASE_URL`, `SYNC_DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `TEST_REDIS_URL`, and the password apart in `REDIS_PASSWORD`, as the API wants it), which the pipeline reads back into the environment of every later stage.
- **Migrations.** `scripts/migrate.sh`: the `geodata` chain, then the `app` chain.
- **API tests.** `scripts/test-coverage.sh`: 100 % of the suite and of the changed lines.
- **Vision tests.** `jenkins/vision-coverage.sh`: the 100 % gate of `services/vision/pyproject.toml`.
- **Web.** `pnpm build`, then `scripts/test-web-coverage.sh`. While `apps/web` does not exist the stage says so and is skipped.
- **Lint.** `scripts/lint.sh`: the format check first, then lint rules, types, shell and Markdown.
- **Security gate (blocking).** `scripts/security-gate.sh`: gitleaks over the tree and the full history, critical advisories in production dependencies.
- **Audit (advisory).** `scripts/audit.sh`: findings make the build unstable, never failed.
- **SonarQube.** On `SONAR_BRANCH` (default `main`) and whenever `RUN_SONAR` is ticked. A failed gate, or a server that cannot be reached, makes the build unstable.

## Build parameters

A blank string means "use the value from `jenkins.env`, or from the Jenkins job or global variable of the same name".

| Parameter              | Default | Purpose                                                        |
| ---------------------- | ------- | -------------------------------------------------------------- |
| `RUN_SONAR`            | `false` | Analyse with SonarQube although the branch is not `main`       |
| `RUN_AUDIT`            | `true`  | Run the advisory audit                                         |
| `SONAR_HOST_URL`       | blank   | SonarQube address                                              |
| `SONAR_PROJECT_KEY`    | blank   | SonarQube project key                                          |
| `SONAR_CREDENTIALS_ID` | blank   | Id of the secret-text credential holding the token             |
| `NODE_TOOL_NAME`       | blank   | Name of the NodeJS tool that provides Node 24                  |
| `ZULIP_STREAM`         | blank   | Zulip stream for the result                                    |
| `ZULIP_TOPIC`          | blank   | Zulip topic for the result                                     |
| `CI_PG_IMAGE`          | blank   | Database image of the build                                    |
| `CI_REDIS_IMAGE`       | blank   | Redis image of the build                                       |
| `CI_PYTEST_WORKERS`    | blank   | Parallel pytest workers, each on its own database; 0 is serial |

## Running the pieces by hand

On a machine with Docker, exactly as a build does:

```bash
bash jenkins/prepare-jenkins-deps.sh --check
bash jenkins/ci-services.sh up                  # PostgreSQL and Redis in containers, writes .env.ci
set -a; . ./.env.ci; set +a                     # DATABASE_URL, SYNC_DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, TEST_REDIS_URL, REDIS_PASSWORD
export ENVIRONMENT=development CI=true
bash scripts/migrate.sh
bash scripts/test-coverage.sh                   # API
bash jenkins/vision-coverage.sh                 # vision
bash jenkins/ci-services.sh down

SONAR_HOST_URL=https://sonar.example.org bash jenkins/sonar-scan.sh --dry-run   # what would be analysed
```

`ci-services.sh` also has `doctor` (can this agent run containers), `sweep` (remove containers of builds that never reached `down`, older than `CI_SWEEP_MAX_AGE`) and `logs`.

## Troubleshooting

- **`Cannot talk to the docker daemon`** The agent user is not in the `docker` group, or the agent was not restarted after it was added. See [docs/JENKINS_SETUP.md](../docs/JENKINS_SETUP.md).
- **`PostgreSQL did not become ready`, `Redis did not answer`** `ci-services.sh up` prints the last 100 lines of the container log. On a cold agent the image is pulled first; raise `CI_WAIT_SECONDS` only if the log shows it was still starting.
- **`the CI database image is missing extensions`** `CI_PG_IMAGE` does not bundle one of the nine extensions. Use an image that carries PostGIS, pgvector and TimescaleDB for PostgreSQL 18.
- **`SonarQube skipped: SONAR_HOST_URL is not set`** Set the address (see the table above); with `RUN_SONAR` ticked a blank address fails the stage instead.
- **A directory is "not analysed, not there yet"** `sonar-scan.sh` drops a source or test directory that does not exist, `apps/web` for one, instead of letting the scanner stop.
