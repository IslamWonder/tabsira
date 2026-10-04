#!/usr/bin/env bash
# Provision a developer machine running Ubuntu (or a derivative such as Linux
# Mint) for TABSIRA: the database server with its extensions, the quality tools,
# and http://tabsira.test. Everything runs natively; Docker is not needed.
#
#   1. base packages
#   2. PostgreSQL 18 + postgis, pgvector, TimescaleDB, preloaded libraries
#                                                       (scripts/install-postgres.sh)
#   3. shfmt, shellcheck, gitleaks, typos               (scripts/install-quality-tools.sh)
#   4. role, databases, schemas, extensions, .env       (scripts/setup-db.sh)
#   5. nginx on port 80 for tabsira.test                (scripts/setup-nginx-local.sh)
#
# Node 24, pnpm and uv are prerequisites that are checked, not installed: they
# are personal choices (nvm, fnm, brew). Install them, then run `make install`.
#
# Idempotent. Needs sudo. Restarts PostgreSQL once when its preloaded libraries
# have to change.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

require_ubuntu
require_sudo

banner "1/5 Base packages"
# A repository of someone else's that fails to update must not stop us.
as_root apt-get update -y || warn "apt-get update reported errors; continuing"
apt_install ca-certificates curl gnupg git make jq openssl

banner "2/5 PostgreSQL and its extensions"
bash "$SCRIPT_DIR/install-postgres.sh"

banner "3/5 Quality tools"
bash "$SCRIPT_DIR/install-quality-tools.sh" shfmt shellcheck gitleaks typos

banner "4/5 Database"
bash "$SCRIPT_DIR/setup-db.sh"

banner "5/5 nginx for tabsira.test"
bash "$SCRIPT_DIR/setup-nginx-local.sh"

banner "Prerequisites"
if have node && [[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 24 ]]; then
	ok "node $(node --version)"
else
	warn "Node 24 or newer is missing (see .nvmrc): install it with nvm, fnm or your package manager."
fi
if have pnpm; then
	ok "pnpm $(pnpm --version)"
else
	warn "pnpm is missing: npm install -g pnpm (the version is pinned in package.json)"
fi
if have uv; then
	ok "$(uv --version)"
else
	warn "uv is missing: https://docs.astral.sh/uv/getting-started/installation/"
fi

ok "Development machine provisioned."
cat <<EOF

Next steps:
  1. make install     dependencies and git hooks
  2. make migrate     geodata chain, then app chain
  3. make dev         api + web with reload
  4. http://tabsira.test  (API: http://api.tabsira.test)
EOF
