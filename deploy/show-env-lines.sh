#!/usr/bin/env bash
# Print the lines for the application host's environment file again, from what the
# data-host provisioning kept: the database and Redis addresses and passwords.
#
# Run as root on the data host, after deploy/provision-postgres.sh and
# deploy/provision-redis.sh:
#   sudo deploy/show-env-lines.sh
#
# The passwords are secrets: do not paste this output into a chat or a ticket. Put it
# in /opt/tabsira/shared/.env on the application host (mode 0600), then run
# deploy/deploy.sh --check there.

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

PG_FILE="${CREDENTIALS_FILE_POSTGRES:-/etc/tabsira/postgres.env}"
REDIS_FILE="${CREDENTIALS_FILE_REDIS:-/etc/tabsira/redis.env}"
[[ $EUID -eq 0 ]] || die "Run as root (sudo): the credential files are root only."

# KEY from a credentials file; the files are KEY=VALUE lines written by the provisioning scripts.
get() { env_get "$1" "$2"; }

if [[ -r "$PG_FILE" ]]; then
	host="$(get "$PG_FILE" DB_HOST)"
	port="$(get "$PG_FILE" DB_PORT)"
	name="$(get "$PG_FILE" DB_NAME)"
	user="$(get "$PG_FILE" DB_USER)"
	password="$(get "$PG_FILE" DB_PASSWORD)"
	echo "DATABASE_URL=postgresql+asyncpg://$user:$password@$host:$port/$name"
	echo "SYNC_DATABASE_URL=postgresql+psycopg://$user:$password@$host:$port/$name"
else
	warn "No $PG_FILE: run deploy/provision-postgres.sh on this host first."
fi
if [[ -r "$REDIS_FILE" ]]; then
	echo "REDIS_URL=redis://$(get "$REDIS_FILE" REDIS_HOST):$(get "$REDIS_FILE" REDIS_PORT)/0"
	echo "REDIS_PASSWORD=$(get "$REDIS_FILE" REDIS_PASSWORD)"
else
	warn "No $REDIS_FILE: run deploy/provision-redis.sh on this host first."
fi
