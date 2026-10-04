#!/usr/bin/env bash
# HTTP checks against a running app (make smoke): the main pages and API routes.
#
#   make smoke                                   # http://tabsira.test, with the write check
#   SITE_URL=https://tabsira.me API_URL=https://api.tabsira.me make smoke   # read-only
#
# One line per check, then a summary; exits 1 when any check failed.
# SMOKE_READ_ONLY=1 skips the write check; a host that does not end in .test is
# read-only whatever the variable says, so production never gets data from here.
set -uo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SITE_URL="${SITE_URL:-http://tabsira.test}"
API_URL="${API_URL:-http://api.tabsira.test}"
SITE_URL="${SITE_URL%/}"
API_URL="${API_URL%/}"
require_cmd curl "Install curl."

# Local development is plain HTTP (decision 49). A machine that still serves a
# .test name over https with a mkcert certificate is trusted through mkcert's
# root file, so the checks work there too.
CURL_TLS=()
if [[ "$API_URL" == https://*.test ]] && have mkcert; then
	ca_root="$(mkcert -CAROOT 2>/dev/null || true)/rootCA.pem"
	if [[ -f "$ca_root" ]]; then
		CURL_TLS=(--cacert "$ca_root")
	fi
fi

read_only=0
if [[ "${SMOKE_READ_ONLY:-}" == "1" || "$API_URL" != *.test ]]; then
	read_only=1
fi

passed=0
failed=0
BODY=""
STATUS=""

pass() {
	printf 'ok    %s\n' "$1"
	passed=$((passed + 1))
}
fail() {
	printf 'FAIL  %s: %s\n' "$1" "$2"
	failed=$((failed + 1))
}

# fetch METHOD URL [curl args...]: sets STATUS and BODY ("000" when unreachable).
fetch() {
	local method="$1" url="$2" out
	shift 2
	out="$(curl -sS --max-time 20 "${CURL_TLS[@]+"${CURL_TLS[@]}"}" -X "$method" \
		-w $'\n%{http_code}' "$@" "$url" 2>/dev/null)" || out=$'\n000'
	STATUS="${out##*$'\n'}"
	BODY="${out%$'\n'*}"
}

# expect_status NAME STATUS: fail with the status actually received.
expect_status() {
	if [[ "$STATUS" == "$2" ]]; then
		return 0
	fi
	fail "$1" "expected $2, got $STATUS"
	return 1
}

# expect_body NAME TEXT: fail when the body lacks the text.
expect_body() {
	if [[ "$BODY" == *"$2"* ]]; then
		return 0
	fi
	fail "$1" "body lacks: $2"
	return 1
}

# web_page PATH TITLE [STATUS]: status, <title> and the Arabic right-to-left root.
web_page() {
	local name="GET $1"
	fetch GET "$SITE_URL$1"
	expect_status "$name" "${3:-200}" || return 0
	expect_body "$name" "<title>$2</title>" || return 0
	expect_body "$name" 'lang="ar" dir="rtl"' || return 0
	pass "$name"
}

# web_file PATH: the file answers 200 with something in it.
web_file() {
	local name="GET $1"
	fetch GET "$SITE_URL$1"
	expect_status "$name" 200 || return 0
	if [[ -z "$BODY" ]]; then
		fail "$name" "empty body"
		return 0
	fi
	pass "$name"
}

# api_get PATH TEXT: 200 and the body holds TEXT.
api_get() {
	local name="GET $1"
	fetch GET "$API_URL$1"
	expect_status "$name" 200 || return 0
	expect_body "$name" "$2" || return 0
	pass "$name"
}

web_checks() {
	web_page / 'تبصرة · انظر إلى العالم بعين الوحي'
	web_page /signin 'الدخول · تبصرة'
	web_page /signup 'إنشاء حساب · تبصرة'
	web_page /terms 'شروط الاستخدام · تبصرة'
	web_page /privacy 'سياسة الخصوصية · تبصرة'
	web_page /support 'الدعم · تبصرة'
	web_file /robots.txt
	web_file /llms.txt
	web_file /manifest.webmanifest
	web_page /smoke-no-such-page 'لم نجد هذه الصفحة · تبصرة' 404
}

api_checks() {
	api_get /health '"status":"ok"'
	# /legal is not served by every build; absent is not a failure.
	fetch GET "$API_URL/legal"
	if [[ "$STATUS" == "404" ]]; then
		printf 'skip  GET /legal: not present\n'
	elif expect_status "GET /legal" 200; then
		pass "GET /legal"
	fi
	api_get /auth/providers '"providers"'
	api_get /consent/policy '"policy_version"'
	# A scripture read carries its stored hash; the text itself is not compared here.
	api_get /scripture/quran/1/1 '"sha256":"'
	api_get /sitemap '"sections"'

	# A browser request from a foreign origin must be refused before any route runs.
	fetch POST "$API_URL/consent" -H 'Origin: https://smoke-foreign.example' \
		-H 'Content-Type: application/json' -d '{}'
	if expect_status "cross-origin POST /consent" 403; then
		pass "cross-origin POST /consent refused"
	fi

	fetch GET "$API_URL/admin"
	if expect_status "GET /admin on the API host" 404; then
		pass "GET /admin on the API host is 404"
	fi
}

write_checks() {
	if [[ $read_only == 1 ]]; then
		printf 'skip  POST /consent: read-only run\n'
		return 0
	fi
	fetch POST "$API_URL/consent" -H 'Content-Type: application/json' \
		-d '{"analytics":false,"behaviour":false}'
	if [[ "$STATUS" != "200" && "$STATUS" != "201" ]]; then
		fail "POST /consent" "expected 200 or 201, got $STATUS"
	elif expect_body "POST /consent" '"consent_id"'; then
		pass "POST /consent (necessary only)"
	fi
}

# SCAN ROUTES: add the scan checks here once the scan workflow merges. Start with
# a rain tutorial read, `api_get /tutorial/rain <text>`, printed as "prepared":
# it is a prepared example, never live analysis (AGENTS.md).

mode=""
if [[ $read_only == 1 ]]; then
	mode=" (read-only)"
fi
printf 'smoke: site %s, api %s%s\n' "$SITE_URL" "$API_URL" "$mode"
web_checks
api_checks
write_checks

printf 'smoke: %d ok, %d failed\n' "$passed" "$failed"
[[ $failed == 0 ]]
