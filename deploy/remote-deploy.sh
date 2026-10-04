#!/usr/bin/env bash
# Deploy a commit to the production application host over ssh. Run by the
# Jenkins deploy stage (or by hand); it runs `tabsira-deploy` on the host, which
# fetches the commit and runs deploy/deploy.sh there. Nothing is built here.
#
# No host, user, key or password lives in git. They come from the environment
# (Jenkins variables and credentials):
#   DEPLOY_HOST        host name or address of the application host (required)
#   DEPLOY_USER        the application user (required)
#   DEPLOY_PORT        ssh port (default 22)
#   DEPLOY_HOST_KEY    the host's PUBLIC key line, "<host> ssh-ed25519 AAAA..."
#                      as `ssh-keyscan -t ed25519 <host>` prints it, verified
#                      once by the owners (required: there is no trust on first use)
#   DEPLOY_KEY_FILE    private key file; Jenkins binds it from an ssh credential
#   DEPLOY_REF         commit to deploy (default: GIT_COMMIT, else origin/main)
#
# Usage: deploy/remote-deploy.sh [--dry-run]
#   --dry-run   print the ssh command, connect nowhere

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

[[ "${1:-}" == "--dry-run" ]] && set_dry_run
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_REF="${DEPLOY_REF:-${GIT_COMMIT:-origin/main}}"
: "${DEPLOY_HOST:?DEPLOY_HOST is not set}"
: "${DEPLOY_USER:?DEPLOY_USER is not set}"
: "${DEPLOY_HOST_KEY:?DEPLOY_HOST_KEY is not set (the public key line of the host)}"
[[ "$DEPLOY_REF" =~ ^[A-Za-z0-9._/-]+$ ]] || die "DEPLOY_REF '$DEPLOY_REF' is not a plain commit, tag or branch name."

KNOWN_HOSTS="$(mktemp)"
trap 'rm -f "$KNOWN_HOSTS"' EXIT
printf '%s\n' "$DEPLOY_HOST_KEY" >"$KNOWN_HOSTS"

ssh_args=(-p "$DEPLOY_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KNOWN_HOSTS")
[[ -z "${DEPLOY_KEY_FILE:-}" ]] || ssh_args+=(-i "$DEPLOY_KEY_FILE" -o IdentitiesOnly=yes)

remote_args=(tabsira-deploy --ref "$DEPLOY_REF")
is_dry && remote_args+=(--dry-run)

if is_dry; then
	log "Would run: ssh ${ssh_args[*]} $DEPLOY_USER@$DEPLOY_HOST ${remote_args[*]}"
	ok "Dry run complete: nothing was contacted."
	exit 0
fi
log "Deploying $DEPLOY_REF to $DEPLOY_HOST"
# shellcheck disable=SC2029  # the remote command is meant to be expanded here
ssh "${ssh_args[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "${remote_args[@]}"
