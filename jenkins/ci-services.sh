#!/usr/bin/env bash
# Start this build's database and Redis as containers, and take them down again.
#
#   ci-services.sh doctor   check the agent can run containers, and report the images
#   ci-services.sh up       start PostgreSQL and Redis, set them up, write .env.ci
#   ci-services.sh down     remove this build's containers and their volumes
#   ci-services.sh sweep    remove containers left behind by builds that never reached down
#   ci-services.sh logs     write the container logs into .ci_logs for archiving
#
# Every build owns its servers: nothing is shared, so builds cannot collide and
# there is no password to store. The passwords are generated per build and die
# with the containers, which listen on 127.0.0.1 only, on ports the kernel
# picks (a host port cannot be known until the container runs).
#
# The database image (CI_PG_IMAGE, default in jenkins/jenkins.env) bundles
# PostgreSQL 18 with PostGIS, pgvector and the TimescaleDB Community build, the
# same three that scripts/install-postgres.sh installs on a host. The role, the
# three databases, the schemas and the nine extensions are what
# scripts/setup-db.sh makes; their SQL is in jenkins/ci-postgres/. Redis
# (CI_REDIS_IMAGE) runs with a password, as production does (decision 22), and
# no persistence.
#
# `up` writes ${WORKSPACE}/.env.ci, which the Jenkinsfile reads back with
# readProperties and a shell reads with `set -a; . .env.ci; set +a`. The name
# is covered by .gitignore (.env.*) and by the allowlist of .gitleaks.toml.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci-env.sh"

WORKSPACE="${WORKSPACE:-$ROOT_DIR}"
ENV_FILE="$WORKSPACE/.env.ci"
SQL_DIR="$SCRIPT_DIR/ci-postgres"
DATABASES=(tabsira tabsira_test tabsira_template)
LABEL="tabsira.ci=1"

# The container is named after the job and the build number, so up, down and logs
# find it from separate stages. A multibranch JOB_NAME arrives as
# "tabsira/main" or "tabsira/feature%2Fx": squash it to what Docker accepts.
default_project() {
	local raw
	raw="$(printf '%s-%s' "${JOB_NAME:-local}" "${BUILD_NUMBER:-0}" |
		tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed -E 's/^-+//; s/-+$//')"
	printf 'tabsira-ci-%s' "${raw:0:48}"
}
CONTAINER="${TABSIRA_CI_CONTAINER:-$(default_project)}"
REDIS_CONTAINER="${CONTAINER}-redis"

require_docker() {
	have docker || die "docker is not installed on this agent."
	docker info >/dev/null 2>&1 ||
		die "Cannot talk to the docker daemon. Add the agent user to the docker group ('sudo usermod -aG docker jenkins') and restart the agent: group membership is fixed when the session starts, so it does not reach this build."
}

# Seconds in a duration such as 90m, 4h or 2d (a bare number is seconds).
duration_seconds() {
	local spec="$1" number unit
	[[ "$spec" =~ ^([0-9]+)([smhd]?)$ ]] || die "CI_SWEEP_MAX_AGE must look like 90m, 4h or 2d (got '$spec')"
	number="${BASH_REMATCH[1]}"
	unit="${BASH_REMATCH[2]:-s}"
	case "$unit" in
	s) echo "$number" ;;
	m) echo $((number * 60)) ;;
	h) echo $((number * 3600)) ;;
	d) echo $((number * 86400)) ;;
	esac
}

# psql inside the container as the postgres superuser, over the local socket.
# From stdin or with -c; the password of the application role goes in by stdin.
psql_admin() {
	local db="$1"
	shift
	docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U postgres -d "$db" "$@"
}

wait_for_postgres() {
	local waited=0 limit="${CI_WAIT_SECONDS:-300}"
	# Over TCP on purpose, not the socket: the entrypoint runs a temporary
	# socket-only server while it initialises, and the socket would report
	# ready before the extensions are installed. Only the real server listens on TCP.
	while ((waited < limit)); do
		if docker exec "$CONTAINER" pg_isready -q -h 127.0.0.1 -U postgres >/dev/null 2>&1; then
			return 0
		fi
		if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)" != "true" ]]; then
			return 1
		fi
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

# Redis in its own container. The password goes in through the environment and
# is read by the shell inside the container, so it is not on the command line of
# a process anybody can list. No persistence: nothing in a build survives it.
start_redis() {
	local image="$1" password="$2"
	if ! docker image inspect "$image" >/dev/null 2>&1; then
		log "Pulling $image (a cold agent does this once)"
		docker pull --quiet "$image" >/dev/null || die "Could not pull $image."
	fi
	log "Starting $image as $REDIS_CONTAINER"
	export REDIS_PASSWORD="$password"
	docker run -d --name "$REDIS_CONTAINER" \
		--label "$LABEL" \
		--label "tabsira.ci.build_url=${BUILD_URL:-local}" \
		--publish 127.0.0.1::6379 \
		--env REDIS_PASSWORD \
		"$image" sh -c 'exec redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"' >/dev/null ||
		die "docker could not start $image."
	unset REDIS_PASSWORD
}

wait_for_redis() {
	local password="$1" waited=0 limit="${CI_WAIT_SECONDS:-300}"
	export REDISCLI_AUTH="$password"
	while ((waited < limit)); do
		if [[ "$(docker exec --env REDISCLI_AUTH "$REDIS_CONTAINER" redis-cli ping 2>/dev/null || true)" == "PONG" ]]; then
			unset REDISCLI_AUTH
			return 0
		fi
		if [[ "$(docker inspect -f '{{.State.Running}}' "$REDIS_CONTAINER" 2>/dev/null || echo false)" != "true" ]]; then
			break
		fi
		sleep 1
		waited=$((waited + 1))
	done
	unset REDISCLI_AUTH
	return 1
}

cmd_up() {
	require_docker
	have openssl || die "openssl is required to generate the build's database password."

	local image="${CI_PG_IMAGE:?CI_PG_IMAGE is not set (see jenkins/jenkins.env)}"
	if ! docker image inspect "$image" >/dev/null 2>&1; then
		log "Pulling $image (a cold agent does this once)"
		docker pull --quiet "$image" >/dev/null || die "Could not pull $image."
	fi

	local redis_image="${CI_REDIS_IMAGE:?CI_REDIS_IMAGE is not set (see jenkins/jenkins.env)}"

	# A retry of the same build starts from nothing.
	docker rm -fv "$CONTAINER" "$REDIS_CONTAINER" >/dev/null 2>&1 || true

	local app_password redis_password
	app_password="$(openssl rand -hex 24)"
	redis_password="$(openssl rand -hex 24)"
	start_redis "$redis_image" "$redis_password"
	POSTGRES_PASSWORD="$(openssl rand -hex 24)"
	export POSTGRES_PASSWORD

	log "Starting $image as $CONTAINER"
	# shared_preload_libraries: the image preloads timescaledb only; the API's
	# first migration needs pg_stat_statements loaded as well (decision 15).
	# fsync, full_page_writes and synchronous_commit are off because this
	# database is deleted when the build ends: nothing for durability to protect.
	# max_locks_per_transaction: the test suite resets both schemas in one transaction.
	# shm_size: Docker's 64 MB default fails parallel queries with "could not
	# resize shared memory segment" once several pytest workers run.
	docker run -d --name "$CONTAINER" \
		--label "$LABEL" \
		--label "tabsira.ci.build_url=${BUILD_URL:-local}" \
		--shm-size 1g \
		--publish 127.0.0.1::5432 \
		--env POSTGRES_PASSWORD \
		--env POSTGRES_USER=postgres \
		--env POSTGRES_DB=postgres \
		"$image" postgres \
		-c shared_preload_libraries=timescaledb,pg_stat_statements \
		-c timescaledb.telemetry_level=off \
		-c fsync=off \
		-c full_page_writes=off \
		-c synchronous_commit=off \
		-c max_connections=200 \
		-c max_locks_per_transaction=256 >/dev/null ||
		die "docker could not start $image."
	unset POSTGRES_PASSWORD

	if ! wait_for_postgres; then
		err "PostgreSQL did not become ready. Last 100 log lines:"
		docker logs --tail 100 "$CONTAINER" 2>&1 || true
		die "Aborting: the build has no database to run against."
	fi

	log "Creating the role and the databases"
	{
		printf '\\set app_password %s\n' "'$app_password'"
		cat "$SQL_DIR/01-role-databases.sql"
	} | psql_admin postgres

	local db
	for db in "${DATABASES[@]}"; do
		log "Schemas and extensions in $db"
		psql_admin "$db" <"$SQL_DIR/02-schemas-extensions.sql"
		psql_admin "$db" <"$SQL_DIR/03-assert.sql"
	done
	# TimescaleDB keeps a background session in every database that accepts
	# connections, and PostgreSQL will not copy a template somebody is connected
	# to: closed to connections, the template can be copied by every test worker.
	psql_admin postgres -c "ALTER DATABASE tabsira_template WITH IS_TEMPLATE true ALLOW_CONNECTIONS false;"
	close_template_sessions

	local port
	port="$(docker port "$CONTAINER" 5432/tcp | head -n 1)"
	port="${port##*:}"
	[[ -n "$port" ]] || die "Could not discover the host port of $CONTAINER."

	verify_as_application_role "$app_password"

	if ! wait_for_redis "$redis_password"; then
		err "Redis did not answer. Last 100 log lines:"
		docker logs --tail 100 "$REDIS_CONTAINER" 2>&1 || true
		die "Aborting: the build has no Redis to run against."
	fi
	local redis_port
	redis_port="$(docker port "$REDIS_CONTAINER" 6379/tcp | head -n 1)"
	redis_port="${redis_port##*:}"
	[[ -n "$redis_port" ]] || die "Could not discover the host port of $REDIS_CONTAINER."

	write_env_file "$app_password" "$port" "$image" "$redis_password" "$redis_port" "$redis_image"
	ok "CI services are up (database 127.0.0.1:$port, Redis 127.0.0.1:$redis_port)"
}

# Closing a database to connections does not end the session the TimescaleDB
# scheduler already holds in it, and one session is enough for PostgreSQL to
# refuse to copy the template. End it; the launcher starts no new one in a
# database that accepts no connections.
close_template_sessions() {
	local attempt left
	for ((attempt = 1; attempt <= 10; attempt++)); do
		psql_admin postgres -tA -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'tabsira_template' AND pid <> pg_backend_pid()" >/dev/null
		left="$(psql_admin postgres -tA -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'tabsira_template'")"
		[[ "$left" == "0" ]] && return 0
		sleep 1
	done
	die "tabsira_template still has $left open session(s), so it cannot be copied."
}

# What the API does at run time, before any test depends on it: connect as the
# application role over TCP with its search_path, and copy the template, which
# is what every pytest-xdist worker does.
verify_as_application_role() {
	local password="$1" path
	export PGPASSWORD="$password"
	path="$(docker exec --env PGPASSWORD "$CONTAINER" psql -X -tA -h 127.0.0.1 -U tabsira -d tabsira_test -c 'SHOW search_path' 2>&1)" ||
		die "the role tabsira cannot connect to tabsira_test: ${path//$password/***}"
	[[ "$path" == "app, corpus, geodata, vectors, public" ]] || die "the search_path of tabsira is '$path', not 'app, corpus, geodata, vectors, public'"
	docker exec --env PGPASSWORD "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -U tabsira -d postgres \
		-c 'CREATE DATABASE tabsira_ci_probe TEMPLATE tabsira_template' \
		-c 'DROP DATABASE tabsira_ci_probe' >/dev/null ||
		die "the role tabsira cannot copy tabsira_template, which every test worker does."
	unset PGPASSWORD
}

write_env_file() {
	local password="$1" port="$2" image="$3" redis_password="$4" redis_port="$5" redis_image="$6" tmp
	tmp="$(mktemp "${ENV_FILE}.XXXXXX")"
	chmod 600 "$tmp"
	{
		echo "TABSIRA_CI_CONTAINER=$CONTAINER"
		echo "TABSIRA_CI_PG_IMAGE=$image"
		echo "TABSIRA_CI_PG_PORT=$port"
		echo "DATABASE_URL=postgresql+asyncpg://tabsira:${password}@127.0.0.1:${port}/tabsira"
		echo "SYNC_DATABASE_URL=postgresql+psycopg://tabsira:${password}@127.0.0.1:${port}/tabsira"
		echo "TEST_DATABASE_URL=postgresql+asyncpg://tabsira:${password}@127.0.0.1:${port}/tabsira_test"
		echo "TABSIRA_CI_REDIS_IMAGE=$redis_image"
		echo "TABSIRA_CI_REDIS_PORT=$redis_port"
		echo "REDIS_HOST=127.0.0.1"
		echo "REDIS_PORT=$redis_port"
		echo "REDIS_PASSWORD=$redis_password"
		echo "REDIS_DB=0"
		# The API refuses a Redis address that carries a password (it reads REDIS_PASSWORD
		# above and keeps the address printable), so neither URL names it.
		echo "REDIS_URL=redis://127.0.0.1:${redis_port}/0"
		# Database 1 for tests, the way tabsira_test is the database for tests:
		# a suite that flushes it can never reach what the application keeps in 0.
		echo "TEST_REDIS_URL=redis://127.0.0.1:${redis_port}/1"
	} >"$tmp"
	mv "$tmp" "$ENV_FILE"
	log "Wrote $ENV_FILE (database 127.0.0.1:$port, Redis 127.0.0.1:$redis_port)"
}

cmd_down() {
	have docker || return 0
	log "Removing $CONTAINER and $REDIS_CONTAINER"
	if docker rm -fv "$CONTAINER" "$REDIS_CONTAINER" >/dev/null 2>&1; then
		ok "CI services removed"
	else
		# Never fatal: this runs in the pipeline's finally block, and a container
		# that is already gone is the goal. A real failure is the sweep's job.
		warn "no container $CONTAINER or $REDIS_CONTAINER to remove (or docker refused); the sweep collects leftovers."
	fi
	rm -f "$ENV_FILE"
}

# By label, not by name: a build that was killed leaves a container the next
# build has no name for. Only containers older than CI_SWEEP_MAX_AGE go, so a
# build that is running right now is never touched. (docker ps has no `until`
# filter, so the age is read from each container.)
cmd_sweep() {
	have docker || return 0
	local max now id created started removed=0
	max="$(duration_seconds "${CI_SWEEP_MAX_AGE:-4h}")"
	now="$(date +%s)"
	while IFS= read -r id; do
		[[ -n "$id" ]] || continue
		created="$(docker inspect -f '{{.Created}}' "$id" 2>/dev/null || true)"
		started="$(date -d "$created" +%s 2>/dev/null || true)"
		if [[ -z "$started" ]]; then
			warn "cannot read the age of container $id; leaving it"
			continue
		fi
		if ((now - started > max)); then
			log "Removing leftover $(docker inspect -f '{{.Name}}' "$id" 2>/dev/null || echo "$id") (older than ${CI_SWEEP_MAX_AGE:-4h})"
			docker rm -fv "$id" >/dev/null 2>&1 || warn "could not remove $id"
			removed=$((removed + 1))
		fi
	done < <(docker ps -aq --filter "label=$LABEL" 2>/dev/null || true)
	ok "Sweep complete ($removed removed)"
}

cmd_logs() {
	have docker || return 0
	local out="${WORKSPACE}/.ci_logs"
	mkdir -p "$out"
	docker logs --timestamps "$CONTAINER" >"$out/ci-postgres.log" 2>&1 || true
	docker logs --timestamps "$REDIS_CONTAINER" >"$out/ci-redis.log" 2>&1 || true
	log "Service logs written to $out/ci-postgres.log and $out/ci-redis.log"
}

cmd_doctor() {
	require_docker
	ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"
	local name image
	for name in CI_PG_IMAGE CI_REDIS_IMAGE; do
		image="${!name:-}"
		if [[ -z "$image" ]]; then
			die "$name is not set (see jenkins/jenkins.env)"
		elif docker image inspect "$image" >/dev/null 2>&1; then
			ok "image present: $image"
		else
			warn "image not pulled yet: $image (the first build pulls it)"
		fi
	done
}

case "${1:-}" in
up) cmd_up ;;
down) cmd_down ;;
sweep) cmd_sweep ;;
logs) cmd_logs ;;
doctor) cmd_doctor ;;
*)
	cat <<'USAGE'
Usage: ci-services.sh <doctor|up|down|sweep|logs>

  doctor  Verify the agent can run containers, and report whether the images are there
  up      Start this build's PostgreSQL and Redis, set them up, write .env.ci
  down    Remove the containers and their volumes
  sweep   Remove containers left behind by builds that never reached down
  logs    Write the container logs into .ci_logs for archiving

Environment (defaults in jenkins/jenkins.env):
  CI_PG_IMAGE           image bundling PostgreSQL 18, PostGIS, pgvector and TimescaleDB
  CI_REDIS_IMAGE        Redis image
  CI_WAIT_SECONDS       how long to wait for each server (default 300)
  CI_SWEEP_MAX_AGE      age after which a container is a leftover (default 4h)
  TABSIRA_CI_CONTAINER  database container name (default derived from JOB_NAME and
                        BUILD_NUMBER); Redis is that name plus -redis
USAGE
	exit 1
	;;
esac
