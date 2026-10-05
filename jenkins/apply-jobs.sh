#!/usr/bin/env bash
# Create or update the TABSIRA jobs Jenkins does not discover by itself.
#
#   JENKINS_USER=<user> JENKINS_TOKEN=<token> ./jenkins/apply-jobs.sh [--dry-run]
#
# Each job is jenkins/<name>.xml.tmpl with the text of its Jenkinsfile written
# inline (@SCRIPT@), like the other deploy jobs on the controller: the job clones
# nothing, so it needs no access to the repository. The job on the controller is
# a copy: run this again after every change to a Jenkinsfile.* or a template.
# Idempotent: an existing job has its configuration replaced.
set -Eeuo pipefail
# The replacement of a pattern substitution must stay literal (bash 5.2 expands
# `&` in it by default), and the escaped script is full of `&amp;`.
shopt -u patsub_replacement 2>/dev/null || true

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
JENKINS_URL="${JENKINS_URL:-https://jenkins.riadvice.net}"
JENKINS_URL="${JENKINS_URL%/}"

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

render() {
	local template="$1" display="$2" script="$3" description="$4"
	local text
	text="$(<"$template")"
	text="${text//@DISPLAY@/$(xml_escape "$display")}"
	text="${text//@DESCRIPTION@/$(xml_escape "$description")}"
	text="${text//@SCRIPT@/$(xml_escape "$(<"$REPO_ROOT/$script")")}"
	printf '%s\n' "$text"
}

for entry in "${JOBS[@]}"; do
	IFS='|' read -r name display script description <<<"$entry"
	template="$SCRIPT_DIR/$name.xml.tmpl"
	[[ -f "$template" && -f "$REPO_ROOT/$script" ]] || {
		echo "Missing $template or $script" >&2
		exit 1
	}
	config="$(mktemp)"
	render "$template" "$display" "$script" "$description" >"$config"
	if $DRY_RUN; then
		echo "would apply $name ($script inline, $(wc -l <"$config") lines of configuration)"
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
