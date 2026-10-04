#!/usr/bin/env bash
# Replace the API's gunicorn workers one at a time, never all at once.
# The sequence is TTIN, health check, TTOU, run against release folders.
#
# gunicorn runs N workers behind one listening socket. The unit starts it from
# the `current` link (its --chdir and its python are both spelled through that
# link), so a worker forked after the link moves imports the new release:
#
#   smoke RELEASE   boot RELEASE once on a spare port and wait for
#                   /health/ready, before any live worker is touched.
#   roll            1. TTIN: gunicorn starts one extra worker, which imports the
#                      release `current` now points at.
#                   2. Wait until it has stayed up, answers /health/ready and
#                      its memory maps show files of the new release (a worker
#                      that silently kept the old code stops the roll).
#                   3. TTOU: gunicorn retires its oldest worker gracefully.
#                   4. Repeat until every worker is new, then bring the pool to
#                      API_WORKERS.
#   scale           only bring the pool to API_WORKERS.
#
# The socket never closes and at least N workers serve at every moment.
# Linux only (procps, /proc): it runs on the application host.
#
# Environment: API_PIDFILE (/run/tabsira-api/gunicorn.pid), API_HEALTH_URL,
# API_SMOKE_PORT (18000), API_BOOT_SECONDS (8), API_STEP_TIMEOUT (90),
# API_WORKERS (from the environment file; default: as many as now run).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

load_runtime_settings
API_PIDFILE="${API_PIDFILE:-/run/tabsira-api/gunicorn.pid}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:${API_PORT}/health/ready}"
API_SMOKE_PORT="${API_SMOKE_PORT:-18000}"
API_BOOT_SECONDS="${API_BOOT_SECONDS:-8}"
API_STEP_TIMEOUT="${API_STEP_TIMEOUT:-90}"

MASTER=""
TOTAL=0

healthy() { api_ready "$1"; }

# Worker pids of the master, oldest first (gunicorn retires in that order).
workers() {
	local pids
	pids="$(pgrep -P "$MASTER" | paste -sd, -)" || true
	[[ -n "$pids" ]] || return 0
	ps -o etimes=,pid= -p "$pids" | sort -rn | awk '{print $2}'
}
worker_count() { workers | grep -c . || true; }
age_of() { ps -o etimes= -p "$1" 2>/dev/null | tr -d ' ' || echo 0; }

# Does worker $1 run the release `current` points at? /proc/PID/maps names the
# real paths of the files it loaded, so the venv of the live release must show.
runs_current_release() {
	local real
	real="$(real_dir "$CURRENT_LINK")"
	grep -qF "$real/apps/api/" "/proc/$1/maps" 2>/dev/null
}

# ─── Pre-flight ─────────────────────────────────────────────────────
smoke() {
	local release="$1" pid deadline log_file="${TMPDIR:-/tmp}/tabsira-api-smoke.log"
	[[ -x "$release/apps/api/.venv/bin/python" ]] || die "No virtual environment in $release/apps/api."
	if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:${API_SMOKE_PORT}/" 2>/dev/null; then
		die "Port ${API_SMOKE_PORT} is already in use; set API_SMOKE_PORT to a free one."
	fi
	log "Pre-flight: booting $(basename "$release") on 127.0.0.1:${API_SMOKE_PORT}"
	(
		cd "$release/apps/api" &&
			exec .venv/bin/python -m gunicorn src.main:app \
				-c "$release/deploy/gunicorn.conf.py" --chdir "$release/apps/api" \
				--workers 1 --bind "127.0.0.1:${API_SMOKE_PORT}" --graceful-timeout 5
	) >"$log_file" 2>&1 &
	pid=$!
	deadline=$((SECONDS + API_STEP_TIMEOUT))
	until kill -0 "$pid" 2>/dev/null && healthy "http://127.0.0.1:${API_SMOKE_PORT}/health/ready"; do
		if ! kill -0 "$pid" 2>/dev/null || ((SECONDS >= deadline)); then
			kill "$pid" 2>/dev/null || true
			wait "$pid" 2>/dev/null || true
			err "The new code did not become ready. Last lines of its log:"
			tail -n 20 "$log_file" >&2 || true
			die "Pre-flight failed; no live worker was touched."
		fi
		sleep 1
	done
	kill -TERM "$pid" 2>/dev/null || true
	wait "$pid" 2>/dev/null || true
	ok "Pre-flight passed: the new code boots and is ready."
}

find_master() {
	[[ -f "$API_PIDFILE" ]] || die "No gunicorn pid file at $API_PIDFILE. Is the API running (systemctl status $API_UNIT)?"
	MASTER="$(cat "$API_PIDFILE")"
	kill -0 "$MASTER" 2>/dev/null || die "gunicorn master $MASTER from $API_PIDFILE is not running."
}

# ─── One worker at a time ───────────────────────────────────────────
replace_one() {
	local before new_pid="" pid deadline seen_count=0 seen=" "
	before=" $(workers | tr '\n' ' ') "
	kill -TTIN "$MASTER"
	deadline=$((SECONDS + API_STEP_TIMEOUT))
	while :; do
		new_pid=""
		for pid in $(workers); do
			[[ "$before" == *" $pid "* ]] && continue
			new_pid=$pid
			if [[ "$seen" != *" $pid "* ]]; then
				seen="$seen$pid "
				seen_count=$((seen_count + 1))
			fi
		done
		# A worker that crashes at boot is respawned under a new pid; a few
		# of those mean the code cannot start and waiting will not help.
		((seen_count > 3)) && break
		if [[ -n "$new_pid" ]] && (($(age_of "$new_pid") >= API_BOOT_SECONDS)) && healthy "$API_HEALTH_URL"; then
			break
		fi
		((SECONDS >= deadline)) && break
		sleep 1
	done

	if [[ -z "$new_pid" ]] || ((seen_count > 3)) || ! kill -0 "$new_pid" 2>/dev/null ||
		(($(age_of "$new_pid") < API_BOOT_SECONDS)); then
		kill -TTOU "$MASTER" || true
		die "A new worker did not come up healthy; stopping before any other worker is replaced."
	fi
	if ! runs_current_release "$new_pid"; then
		kill -TTOU "$MASTER" || true
		die "Worker $new_pid is healthy but did not load the release $(release_id_of "$CURRENT_LINK"); stopping. Restart the API outright: sudo systemctl restart $API_UNIT."
	fi

	kill -TTOU "$MASTER"
	deadline=$((SECONDS + API_STEP_TIMEOUT))
	until (($(worker_count) == TOTAL)); do
		((SECONDS < deadline)) || die "No worker retired within ${API_STEP_TIMEOUT}s."
		sleep 1
	done
	kill -0 "$new_pid" 2>/dev/null || die "The new worker $new_pid exited while the old one retired."
	log "  a worker retired, $new_pid serving"
}

# ─── Pool size ──────────────────────────────────────────────────────
add_one() {
	local before new_pid pid deadline
	before=" $(workers | tr '\n' ' ') "
	kill -TTIN "$MASTER"
	deadline=$((SECONDS + API_STEP_TIMEOUT))
	while :; do
		new_pid=""
		for pid in $(workers); do
			[[ "$before" == *" $pid "* ]] || new_pid=$pid
		done
		if [[ -n "$new_pid" ]] && (($(age_of "$new_pid") >= API_BOOT_SECONDS)) && healthy "$API_HEALTH_URL"; then
			log "  worker $new_pid added"
			return 0
		fi
		if ((SECONDS >= deadline)); then
			kill -TTOU "$MASTER" || true
			die "An added worker did not come up healthy; the pool is back to its size."
		fi
		sleep 1
	done
}

retire_one() {
	local want="$1" deadline
	kill -TTOU "$MASTER"
	deadline=$((SECONDS + API_STEP_TIMEOUT))
	until (($(worker_count) == want)); do
		((SECONDS < deadline)) || die "No worker retired within ${API_STEP_TIMEOUT}s."
		sleep 1
	done
	log "  a worker retired"
}

scale_to_setting() {
	local running wanted
	running="$(worker_count)"
	wanted="${API_WORKERS:-$running}"
	[[ "$wanted" =~ ^[1-9][0-9]*$ ]] || die "API_WORKERS must be a positive number, not '$wanted'."
	((running == wanted)) && return 0
	log "Scaling the API from $running to $wanted worker(s), one at a time"
	while (($(worker_count) < wanted)); do add_one; done
	while (($(worker_count) > wanted)); do retire_one $(($(worker_count) - 1)); done
	healthy "$API_HEALTH_URL" || die "The API is not ready after scaling."
	ok "The API runs $wanted worker(s)."
}

roll() {
	local i
	find_master
	TOTAL="$(worker_count)"
	((TOTAL > 0)) || die "gunicorn master $MASTER has no workers."
	log "Replacing $TOTAL worker(s) one at a time (master $MASTER)"
	for ((i = 1; i <= TOTAL; i++)); do
		log "Worker $i of $TOTAL"
		replace_one
	done
	healthy "$API_HEALTH_URL" || die "The API is not ready after the rolling reload."
	ok "All $TOTAL API workers now run $(release_id_of "$CURRENT_LINK")."
	scale_to_setting
}

case "${1:-}" in
smoke)
	[[ -n "${2:-}" ]] || die "usage: api-roll.sh smoke RELEASE_DIR"
	smoke "$2"
	;;
roll) roll ;;
scale)
	find_master
	scale_to_setting
	;;
*) die "usage: api-roll.sh smoke RELEASE_DIR | roll | scale" ;;
esac
