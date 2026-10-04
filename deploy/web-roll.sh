#!/usr/bin/env bash
# Put a new web build live with no downtime. Ported from the reference project's
# scripts/web-rolling-deploy.sh, with the release folders owned by deploy.sh.
#
#   assemble RELEASE  copy the standalone build of RELEASE/apps/web/.next into
#                     RELEASE/web, and its static files into the shared static
#                     folder nginx serves. That folder keeps the files of older
#                     builds: a tab opened before the deploy still asks for the
#                     old chunk names. Nothing is overwritten (a chunk name is
#                     a content hash) and every file this build uses is touched.
#   smoke RELEASE     boot RELEASE/web on a spare port and wait for the health
#                     path; a build that cannot start is caught before any live
#                     process is touched.
#   roll              reload the pm2 instances strictly in sequence, each
#                     online and healthy before the next is touched; the others
#                     serve meanwhile. Starts the app when pm2 has none.
#   prune             remove static files no recent build references.
#
# Environment: WEB_PORT (3000), WEB_SMOKE_PORT (3100), WEB_INSTANCES (2 or
# `max`), WEB_HEALTH_PATH (/), WEB_BOOT_SECONDS (5), WEB_STEP_TIMEOUT (90),
# WEB_STATIC_DAYS (7).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

load_runtime_settings
WEB_SMOKE_PORT="${WEB_SMOKE_PORT:-3100}"
WEB_HEALTH_PATH="${WEB_HEALTH_PATH:-/}"
WEB_BOOT_SECONDS="${WEB_BOOT_SECONDS:-5}"
WEB_STEP_TIMEOUT="${WEB_STEP_TIMEOUT:-90}"
WEB_STATIC_DAYS="${WEB_STATIC_DAYS:-7}"
PM2_CONFIG="${PM2_CONFIG:-$CURRENT_LINK/deploy/ecosystem.config.cjs}"

# The Node processes read the environment file themselves (the pm2 config),
# but `pm2 reload --update-env` takes this shell's environment: hand it the
# file's values, as deploy.sh does.
export_env_file() {
	[[ -f "$ENV_FILE" ]] || return 0
	set -a
	# shellcheck disable=SC1090
	. "$ENV_FILE"
	set +a
}

healthy() { curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$1${WEB_HEALTH_PATH}" 2>/dev/null; }

# pm2's process list as JSON and nothing else: the first pm2 command of a user
# prints a banner before the JSON (it once stopped a the reference project deploy).
pm2_jlist() {
	pm2 ping >/dev/null 2>&1 || true
	pm2 jlist 2>/dev/null | grep -E '^\[(\{|\])' | tail -n 1
}

instance_ids() {
	pm2_jlist | node -e '
		let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => {
			for (const p of JSON.parse(s || "[]")) if (p.name === process.argv[1]) console.log(p.pm_id);
		});' "$PM2_APP"
}

# "status uptime_ms" of one pm2 instance.
# shellcheck disable=SC2016  # the ${...} are JavaScript, not shell
instance_state() {
	pm2_jlist | node -e '
		let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => {
			const p = JSON.parse(s || "[]").find((x) => String(x.pm_id) === process.argv[1]);
			console.log(p ? `${p.pm2_env.status} ${Date.now() - p.pm2_env.pm_uptime}` : "missing 0");
		});' "$1"
}

assemble() {
	local release="$1" build="$1/apps/web/.next"
	[[ -f "$build/standalone/apps/web/server.js" ]] ||
		die "No standalone build in $build. Run: pnpm --filter @tabsira/web build"
	mkdir -p "$release/web" "$STATIC_DIR/_next/static"
	cp -a "$build/standalone/." "$release/web/"
	mkdir -p "$release/web/apps/web/.next"
	cp -a "$build/static" "$release/web/apps/web/.next/static"
	[[ -d "$release/apps/web/public" ]] && cp -a "$release/apps/web/public" "$release/web/apps/web/public"
	# Never overwrite, then mark every file this release uses as recently referenced.
	cp -R -n "$release/web/apps/web/.next/static/." "$STATIC_DIR/_next/static/"
	(cd "$release/web/apps/web/.next/static" && find . -type f -print0) |
		(cd "$STATIC_DIR/_next/static" && xargs -0 -n 100 touch -c --)
	chmod -R a+rX "$STATIC_DIR"
	ok "Web build assembled in $release/web"
}

smoke() {
	local release="$1" pid log_file="${TMPDIR:-/tmp}/tabsira-web-smoke.log" deadline
	if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:${WEB_SMOKE_PORT}/" 2>/dev/null; then
		die "Port ${WEB_SMOKE_PORT} is already in use; set WEB_SMOKE_PORT to a free one."
	fi
	log "Pre-flight: booting $(basename "$release") web on 127.0.0.1:${WEB_SMOKE_PORT}"
	(
		cd "$release/web/apps/web" &&
			PORT="$WEB_SMOKE_PORT" HOSTNAME=127.0.0.1 NODE_ENV=production exec node server.js
	) >"$log_file" 2>&1 &
	pid=$!
	deadline=$((SECONDS + WEB_STEP_TIMEOUT))
	until kill -0 "$pid" 2>/dev/null && healthy "$WEB_SMOKE_PORT"; do
		if ! kill -0 "$pid" 2>/dev/null || ((SECONDS >= deadline)); then
			kill "$pid" 2>/dev/null || true
			wait "$pid" 2>/dev/null || true
			err "The new build did not answer ${WEB_HEALTH_PATH}. Last lines of its log:"
			tail -n 20 "$log_file" >&2 || true
			die "Pre-flight failed; no live process was touched."
		fi
		sleep 1
	done
	kill -TERM "$pid" 2>/dev/null || true
	wait "$pid" 2>/dev/null || true
	ok "Pre-flight passed."
}

wanted_instances() {
	if [[ "$WEB_INSTANCES" == "max" ]]; then
		nproc
	elif [[ "$WEB_INSTANCES" =~ ^[1-9][0-9]*$ ]]; then
		echo "$WEB_INSTANCES"
	else
		die "WEB_INSTANCES must be a positive number or 'max', not '$WEB_INSTANCES'."
	fi
}

# Bring the running count to WEB_INSTANCES, after the reload so every process
# already runs the new release.
scale_to_setting() {
	local running="$1" wanted
	wanted="$(wanted_instances)"
	((running == wanted)) && return 0
	log "Scaling $PM2_APP from $running to $wanted instances (WEB_INSTANCES)"
	pm2 scale "$PM2_APP" "$wanted" >/dev/null
	wait_until "$WEB_STEP_TIMEOUT" settled "$wanted" || die "$PM2_APP did not settle at $wanted instances."
	ok "$PM2_APP runs $wanted instances."
}

settled() {
	[[ "$(instance_ids | grep -c . || true)" -eq "$1" ]] && healthy "$WEB_PORT"
}

roll() {
	local ids id state status uptime deadline n=0 total
	export_env_file
	ids="$(instance_ids)"
	if [[ -z "$ids" ]]; then
		log "Starting $PM2_APP ($WEB_INSTANCES instances, cluster mode)"
		pm2 start "$PM2_CONFIG" --only "$PM2_APP"
		pm2 save >/dev/null
		wait_until "$WEB_STEP_TIMEOUT" healthy "$WEB_PORT" || die "$PM2_APP did not answer ${WEB_HEALTH_PATH} after starting."
		ok "$PM2_APP started."
		return
	fi
	total="$(wc -w <<<"$ids" | tr -d ' ')"
	for id in $ids; do
		n=$((n + 1))
		log "Instance $n of $total (pm2 id $id)"
		pm2 reload "$id" --update-env >/dev/null
		deadline=$((SECONDS + WEB_STEP_TIMEOUT))
		while :; do
			state="$(instance_state "$id")"
			status="${state% *}"
			uptime="${state#* }"
			if [[ "$status" == "online" ]] && ((uptime >= WEB_BOOT_SECONDS * 1000)) && healthy "$WEB_PORT"; then
				break
			fi
			((SECONDS < deadline)) || die "pm2 instance $id is '$status' after ${WEB_STEP_TIMEOUT}s; stopping before the next one."
			sleep 1
		done
		log "  instance $id online on $(release_id_of "$CURRENT_LINK")"
	done
	scale_to_setting "$total"
	pm2 save >/dev/null
}

prune_static() {
	find "$STATIC_DIR" -type f -mtime +"$WEB_STATIC_DAYS" -delete 2>/dev/null || true
	find "$STATIC_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
}

case "${1:-}" in
assemble)
	[[ -n "${2:-}" ]] || die "usage: web-roll.sh assemble RELEASE_DIR"
	assemble "$2"
	;;
smoke)
	[[ -n "${2:-}" ]] || die "usage: web-roll.sh smoke RELEASE_DIR"
	smoke "$2"
	;;
roll) roll ;;
prune) prune_static ;;
*) die "usage: web-roll.sh assemble RELEASE_DIR | smoke RELEASE_DIR | roll | prune" ;;
esac
