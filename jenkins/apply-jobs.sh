#!/usr/bin/env bash
# Create or update the TABSIRA jobs Jenkins does not discover by itself.
#
#   JENKINS_USER=<user> JENKINS_TOKEN=<token> ./jenkins/apply-jobs.sh [--dry-run]
#
# Each job reads its Jenkinsfile from the main branch of the Gitea repository
# (jenkins/standalone-job.xml.tmpl). Idempotent: an existing job has its
# configuration replaced, so this is also how a template change is rolled out.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
TEMPLATE="$SCRIPT_DIR/standalone-job.xml.tmpl"
JENKINS_URL="${JENKINS_URL:-https://jenkins.riadvice.net}"
JENKINS_URL="${JENKINS_URL%/}"
REPO_URL="${JENKINS_REPO_URL:-ssh://git@gitea.riadvice.net:32122/RIADVICE/tabsira.git}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# name | display name | Jenkinsfile | description
JOBS=(
	"tabsira-deploy|TABSIRA - Deploy|jenkins/Jenkinsfile.deploy|Deploy TABSIRA to production: ssh to the application host over Netbird, git pull, then deploy/deploy.sh with the parts asked for (api, worker, vision, web; blank = all), then a health check."
)

xml_escape() { printf '%s' "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }

if ! $DRY_RUN; then
	: "${JENKINS_USER:?set JENKINS_USER}"
	: "${JENKINS_TOKEN:?set JENKINS_TOKEN}"
fi

jk() {
	local method="$1" path="$2"
	shift 2
	curl -sS -m 60 -X "$method" -u "$JENKINS_USER:$JENKINS_TOKEN" "$JENKINS_URL$path" "$@"
}

for entry in "${JOBS[@]}"; do
	IFS='|' read -r name display script description <<<"$entry"
	config="$(mktemp)"
	sed -e "s|@NAME@|${name}|g" -e "s|@DISPLAY@|$(xml_escape "$display")|g" -e "s|@SCRIPT@|${script}|g" \
		-e "s|@REPO_URL@|${REPO_URL}|g" -e "s|@DESCRIPTION@|$(xml_escape "$description")|g" \
		"$TEMPLATE" >"$config"
	if $DRY_RUN; then
		echo "would apply $name ($script from $REPO_URL)"
		rm -f "$config"
		continue
	fi
	if [[ "$(jk GET "/job/$name/api/json" -o /dev/null -w '%{http_code}')" == "200" ]]; then
		code="$(jk POST "/job/$name/config.xml" -H "Content-Type: application/xml" --data-binary "@$config" -o /dev/null -w '%{http_code}')"
		verb=updated
	else
		code="$(jk POST "/createItem?name=$name" -H "Content-Type: application/xml" --data-binary "@$config" -o /dev/null -w '%{http_code}')"
		verb=created
	fi
	rm -f "$config"
	[[ "$code" == "200" ]] || {
		echo "Applying $name failed with HTTP $code" >&2
		exit 1
	}
	echo "$verb $name: $JENKINS_URL/job/$name/"
done
