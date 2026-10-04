#!/usr/bin/env bash
# Load the committed defaults of the pipeline (jenkins/jenkins.env).
#
#   source jenkins/ci-env.sh        # exports every key that is not set yet
#
# A variable that is already set and not blank keeps its value: that is how a
# Jenkins job or global environment variable, or a build parameter the
# Jenkinsfile exported, wins over the file. The file is parsed, never sourced:
# only KEY=VALUE lines are read and a value is never run by the shell.

CI_ENV_FILE="${CI_ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/jenkins.env}"

load_ci_defaults() {
	local file="${1:-$CI_ENV_FILE}" line key value
	[[ -f "$file" ]] || {
		printf '[err ] %s is missing\n' "$file" >&2
		return 1
	}
	while IFS= read -r line || [[ -n "$line" ]]; do
		[[ -z "$line" || "$line" == \#* ]] && continue
		[[ "$line" == *=* ]] || continue
		key="${line%%=*}"
		value="${line#*=}"
		[[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || continue
		if [[ -z "${!key:-}" ]]; then
			export "$key=$value"
		fi
	done <"$file"
}

load_ci_defaults
