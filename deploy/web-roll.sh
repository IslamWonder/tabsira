#!/usr/bin/env bash
# Put a new web build live with no downtime, as on the earlier prototype: the build
# gets its own folder, a pre-flight, then the pm2 instances one at a time.
#
#   deploy     after `pnpm --filter @tabsira/web build` in the clone (deploy.sh does both):
#              1. Copy the standalone build into its own folder under
#                 $WEB_RELEASES_DIR/releases. The live processes never read the
#                 clone, so the next build cannot break them.
#              2. Add its /_next/static files to $STATIC_DIR, which nginx serves and
#                 which keeps older builds' files for a few days: a tab opened
#                 before the deploy still asks for the old chunk names.
#              3. Boot the copy once on a spare port and wait for the health path.
#                 A build that cannot start is caught before any live process is touched.
#              4. Point `current` at it (one atomic rename; `previous` keeps the old one).
#              5. Reload the pm2 instances strictly in sequence, each online and
#                 healthy before the next is touched; the others serve meanwhile.
#              6. Prune old copies and static files nothing references any more.
#   rollback   point `current` back at `previous` and reload the same way.
#   prune      step 6 alone.
#
# Environment: WEB_RELEASES_DIR (/srv/tabsira/web), STATIC_DIR (/srv/tabsira/static),
# WEB_PORT (3000), WEB_SMOKE_PORT (3100), WEB_INSTANCES (2 or `max`), WEB_HEALTH_PATH
# (/), WEB_BOOT_SECONDS (5), WEB_STEP_TIMEOUT (90), WEB_KEEP_RELEASES (5),
# WEB_STATIC_DAYS (7).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

load_runtime_settings
WEB_SMOKE_PORT="${WEB_SMOKE_PORT:-3100}"
WEB_HEALTH_PATH="${WEB_HEALTH_PATH:-/}"
WEB_BOOT_SECONDS="${WEB_BOOT_SECONDS:-5}"
WEB_STEP_TIMEOUT="${WEB_STEP_TIMEOUT:-90}"
WEB_KEEP_RELEASES="${WEB_KEEP_RELEASES:-5}"
WEB_STATIC_DAYS="${WEB_STATIC_DAYS:-7}"
PM2_CONFIG="$REPO_DIR/deploy/ecosystem.config.cjs"
BUILD_DIR="$REPO_DIR/apps/web/.next"
RELEASES="$WEB_RELEASES_DIR/releases"
CURRENT="$WEB_RELEASES_DIR/current"
PREVIOUS="$WEB_RELEASES_DIR/previous"
export REPO_DIR ENV_FILE WEB_RELEASES_DIR

# The Node processes read the environment file themselves (the pm2 config), but
# `pm2 reload --update-env` takes this shell's environment: hand it the file's values.
export_env_file() {
	[[ -f "$ENV_FILE" ]] || return 0
	set -a
	# shellcheck disable=SC1090
	. "$ENV_FILE"
	set +a
}

healthy() { curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$1${WEB_HEALTH_PATH}" 2>/dev/null; }

# pm2's process list as JSON and nothing else: the first pm2 command of a user
# prints a banner before the JSON.
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

# ─── 1–2. Its own copy, and the shared static files ────────────────
assemble() {
	local release="$1"
	[[ -f "$BUILD_DIR/standalone/apps/web/server.js" ]] ||
		die "No standalone build in $BUILD_DIR. Run: pnpm --filter @tabsira/web build"
	mkdir -p "$release" "$STATIC_DIR/_next/static"
	cp -a "$BUILD_DIR/standalone/." "$release/"
	mkdir -p "$release/apps/web/.next"
	cp -a "$BUILD_DIR/static" "$release/apps/web/.next/static"
	[[ -d "$REPO_DIR/apps/web/public" ]] && cp -a "$REPO_DIR/apps/web/public" "$release/apps/web/public"
	# Never overwrite (a chunk name is a content hash), then mark every file this build uses as recent.
	# GNU cp 9.3+ warns about -n and names --update=none instead; older GNU and BSD cp know
	# only -n. An unknown value makes cp refuse even --version, so the check copies nothing.
	local keep=(-n)
	cp --update=none --version >/dev/null 2>&1 && keep=(--update=none)
	cp -R "${keep[@]}" "$release/apps/web/.next/static/." "$STATIC_DIR/_next/static/"
	(cd "$release/apps/web/.next/static" && find . -type f -print0) |
		(cd "$STATIC_DIR/_next/static" && xargs -0 -r -n 100 touch -c --)
	chmod -R a+rX "$STATIC_DIR"
	ok "Web build copied to $release"
}

# ─── 3. Pre-flight ──────────────────────────────────────────────────
smoke() {
	local release="$1" pid log_file="${TMPDIR:-/tmp}/tabsira-web-smoke.log" deadline
	if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:${WEB_SMOKE_PORT}/" 2>/dev/null; then
		rm -rf -- "$release"
		die "Port ${WEB_SMOKE_PORT} is already in use; set WEB_SMOKE_PORT to a free one."
	fi
	log "Pre-flight: booting $(basename "$release") on 127.0.0.1:${WEB_SMOKE_PORT}"
	(
		export_env_file
		cd "$release/apps/web" &&
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
			rm -rf -- "$release"
			die "Pre-flight failed; no live process was touched."
		fi
		sleep 1
	done
	kill -TERM "$pid" 2>/dev/null || true
	wait "$pid" 2>/dev/null || true
	ok "Pre-flight passed."
}

# ─── 4. Switch ──────────────────────────────────────────────────────
activate() {
	atomic_link "$1" "$CURRENT"
	log "current -> $(basename "$1")"
}

# ─── 5. One instance at a time ──────────────────────────────────────
wanted_instances() {
	if [[ "$WEB_INSTANCES" == "max" ]]; then
		nproc
	elif [[ "$WEB_INSTANCES" =~ ^[1-9][0-9]*$ ]]; then
		echo "$WEB_INSTANCES"
	else
		die "WEB_INSTANCES must be a positive number or 'max', not '$WEB_INSTANCES'."
	fi
}

settled() {
	[[ "$(instance_ids | grep -c . || true)" -eq "$1" ]] && healthy "$WEB_PORT"
}

# Bring the running count to WEB_INSTANCES, after the reload so every process runs the new build.
scale_to_setting() {
	local running="$1" wanted
	wanted="$(wanted_instances)"
	((running == wanted)) && return 0
	log "Scaling $PM2_APP from $running to $wanted instances (WEB_INSTANCES)"
	pm2 scale "$PM2_APP" "$wanted" >/dev/null
	wait_until "$WEB_STEP_TIMEOUT" settled "$wanted" || die "$PM2_APP did not settle at $wanted instances."
	ok "$PM2_APP runs $wanted instances."
}

reload_in_sequence() {
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
		log "  instance $id online on $(basename "$(real_dir "$CURRENT")")"
	done
	scale_to_setting "$total"
	pm2 save >/dev/null
}

# ─── 6. Prune ───────────────────────────────────────────────────────
prune() {
	local keep_current keep_previous old
	keep_current="$(real_dir "$CURRENT" || true)"
	keep_previous="$(real_dir "$PREVIOUS" || true)"
	# Newest first (the folder name starts with a UTC timestamp); never current or previous.
	if [[ -d "$RELEASES" ]]; then
		for old in $(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +"$((WEB_KEEP_RELEASES + 1))"); do
			[[ "$old" == "$keep_current" || "$old" == "$keep_previous" ]] && continue
			rm -rf -- "$old"
		done
	fi
	# Static files are touched each time a build uses them: age means "no recent build uses it".
	find "$STATIC_DIR" -type f -mtime +"$WEB_STATIC_DAYS" -delete 2>/dev/null || true
	find "$STATIC_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
}

deploy() {
	local release
	mkdir -p "$RELEASES"
	release="$RELEASES/$(date -u +%Y%m%d%H%M%S)-$(git -C "$REPO_DIR" rev-parse --short=12 HEAD)"
	log "Copying the web build to $(basename "$release")"
	assemble "$release"
	smoke "$release"
	[[ -L "$CURRENT" ]] && atomic_link "$(real_dir "$CURRENT")" "$PREVIOUS"
	activate "$release"
	reload_in_sequence
	prune
	ok "Web is live on $(basename "$release")."
}

rollback() {
	[[ -L "$PREVIOUS" ]] || die "No previous web build recorded in $PREVIOUS."
	local target
	target="$(real_dir "$PREVIOUS")" || die "The previous web build is gone."
	warn "Rolling the web back to $(basename "$target")"
	activate "$target"
	reload_in_sequence
	ok "Web rolled back to $(basename "$target")."
}

case "${1:-}" in
deploy) deploy ;;
rollback) rollback ;;
prune) prune ;;
*) die "usage: web-roll.sh deploy | rollback | prune" ;;
esac
