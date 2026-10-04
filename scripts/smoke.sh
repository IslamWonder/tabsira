#!/usr/bin/env bash
# HTTP checks against a running app (make smoke): the main pages and API routes.
#
#   make smoke                                   # http://tabsira.test, with the write check and a trial scan
#   SITE_URL=https://tabsira.me API_URL=https://api.tabsira.me make smoke   # read-only
#
# One line per check, then a summary; exits 1 when any check failed.
# SMOKE_READ_ONLY=1 skips the write check and the trial scan; a host that does
# not end in .test is read-only whatever the variable says, so production never
# gets data from here. The rain scene is read everywhere.
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

# A 64x64 JPEG of one colour, made once with Pillow and kept here as octal
# escapes so the trial scan needs no image tool on the machine (printf %b).
SMOKE_JPEG=''
SMOKE_JPEG+='\0377\0330\0377\0340\0000\0020\0112\0106\0111\0106\0000\0001\0001\0000\0000\0001\0000\0001\0000\0000\0377\0333\0000\0103'
SMOKE_JPEG+='\0000\0033\0022\0024\0027\0024\0021\0033\0027\0026\0027\0036\0034\0033\0040\0050\0102\0053\0050\0045\0045\0050\0121\0072'
SMOKE_JPEG+='\0075\0060\0102\0140\0125\0145\0144\0137\0125\0135\0133\0152\0170\0231\0201\0152\0161\0220\0163\0133\0135\0205\0265\0206'
SMOKE_JPEG+='\0220\0236\0243\0253\0255\0253\0147\0200\0274\0311\0272\0246\0307\0231\0250\0253\0244\0377\0333\0000\0103\0001\0034\0036'
SMOKE_JPEG+='\0036\0050\0043\0050\0116\0053\0053\0116\0244\0156\0135\0156\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244'
SMOKE_JPEG+='\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244'
SMOKE_JPEG+='\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0244\0377\0300\0000\0021\0010\0000\0100\0000\0100\0003'
SMOKE_JPEG+='\0001\0042\0000\0002\0021\0001\0003\0021\0001\0377\0304\0000\0037\0000\0000\0001\0005\0001\0001\0001\0001\0001\0001\0000'
SMOKE_JPEG+='\0000\0000\0000\0000\0000\0000\0000\0001\0002\0003\0004\0005\0006\0007\0010\0011\0012\0013\0377\0304\0000\0265\0020\0000'
SMOKE_JPEG+='\0002\0001\0003\0003\0002\0004\0003\0005\0005\0004\0004\0000\0000\0001\0175\0001\0002\0003\0000\0004\0021\0005\0022\0041'
SMOKE_JPEG+='\0061\0101\0006\0023\0121\0141\0007\0042\0161\0024\0062\0201\0221\0241\0010\0043\0102\0261\0301\0025\0122\0321\0360\0044'
SMOKE_JPEG+='\0063\0142\0162\0202\0011\0012\0026\0027\0030\0031\0032\0045\0046\0047\0050\0051\0052\0064\0065\0066\0067\0070\0071\0072'
SMOKE_JPEG+='\0103\0104\0105\0106\0107\0110\0111\0112\0123\0124\0125\0126\0127\0130\0131\0132\0143\0144\0145\0146\0147\0150\0151\0152'
SMOKE_JPEG+='\0163\0164\0165\0166\0167\0170\0171\0172\0203\0204\0205\0206\0207\0210\0211\0212\0222\0223\0224\0225\0226\0227\0230\0231'
SMOKE_JPEG+='\0232\0242\0243\0244\0245\0246\0247\0250\0251\0252\0262\0263\0264\0265\0266\0267\0270\0271\0272\0302\0303\0304\0305\0306'
SMOKE_JPEG+='\0307\0310\0311\0312\0322\0323\0324\0325\0326\0327\0330\0331\0332\0341\0342\0343\0344\0345\0346\0347\0350\0351\0352\0361'
SMOKE_JPEG+='\0362\0363\0364\0365\0366\0367\0370\0371\0372\0377\0304\0000\0037\0001\0000\0003\0001\0001\0001\0001\0001\0001\0001\0001'
SMOKE_JPEG+='\0001\0000\0000\0000\0000\0000\0000\0001\0002\0003\0004\0005\0006\0007\0010\0011\0012\0013\0377\0304\0000\0265\0021\0000'
SMOKE_JPEG+='\0002\0001\0002\0004\0004\0003\0004\0007\0005\0004\0004\0000\0001\0002\0167\0000\0001\0002\0003\0021\0004\0005\0041\0061'
SMOKE_JPEG+='\0006\0022\0101\0121\0007\0141\0161\0023\0042\0062\0201\0010\0024\0102\0221\0241\0261\0301\0011\0043\0063\0122\0360\0025'
SMOKE_JPEG+='\0142\0162\0321\0012\0026\0044\0064\0341\0045\0361\0027\0030\0031\0032\0046\0047\0050\0051\0052\0065\0066\0067\0070\0071'
SMOKE_JPEG+='\0072\0103\0104\0105\0106\0107\0110\0111\0112\0123\0124\0125\0126\0127\0130\0131\0132\0143\0144\0145\0146\0147\0150\0151'
SMOKE_JPEG+='\0152\0163\0164\0165\0166\0167\0170\0171\0172\0202\0203\0204\0205\0206\0207\0210\0211\0212\0222\0223\0224\0225\0226\0227'
SMOKE_JPEG+='\0230\0231\0232\0242\0243\0244\0245\0246\0247\0250\0251\0252\0262\0263\0264\0265\0266\0267\0270\0271\0272\0302\0303\0304'
SMOKE_JPEG+='\0305\0306\0307\0310\0311\0312\0322\0323\0324\0325\0326\0327\0330\0331\0332\0342\0343\0344\0345\0346\0347\0350\0351\0352'
SMOKE_JPEG+='\0362\0363\0364\0365\0366\0367\0370\0371\0372\0377\0332\0000\0014\0003\0001\0000\0002\0021\0003\0021\0000\0077\0000\0165'
SMOKE_JPEG+='\0024\0121\0132\0020\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000'
SMOKE_JPEG+='\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000'
SMOKE_JPEG+='\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0024\0121\0105\0000\0177\0377\0331'

# json_field KEY: the first string value of KEY in BODY, or nothing. Enough for
# the flat top-level fields of a scan ("id", "status", "outcome", "error_code"),
# which come before any nested object that could repeat the key.
json_field() {
	local rest="${BODY#*\""$1"\":\"}"
	if [[ "$rest" == "$BODY" ]]; then
		return 0
	fi
	printf '%s' "${rest%%\"*}"
}

# The rain scene is prepared, reviewed content read from the store: the check
# says so, because it is never live analysis (AGENTS.md).
rain_check() {
	local name="GET /tutorial/rain"
	fetch GET "$API_URL/tutorial/rain"
	expect_status "$name" 200 || return 0
	expect_body "$name" '"scene":"rain"' || return 0
	expect_body "$name" '"status":"prepared"' || return 0
	expect_body "$name" '"label":"مثال موثّق مُعدّ"' || return 0
	expect_body "$name" '"insights":[{' || return 0
	pass "$name (prepared example, not live analysis)"
}

# One trial scan on a .test host only: the small JPEG above is posted as a new
# guest and the scan is polled until it is done, failed, or 60 s have passed.
# A finished scan passes whatever it found (insights, a clarifying question or
# no relevant evidence); a scan the engine could not run because no model was
# reachable is a skip, since the pipeline, not the app, is unavailable.
trial_scan() {
	local name="POST /scans" image jar scan_id state deadline
	if [[ $read_only == 1 ]]; then
		printf 'skip  %s: the trial scan runs on a .test host only (read-only run)\n' "$name"
		return 0
	fi
	image="$(mktemp)"
	jar="$(mktemp)"
	printf '%b' "$SMOKE_JPEG" >"$image"
	fetch POST "$API_URL/scans" -c "$jar" -b "$jar" \
		-F "image=@$image;type=image/jpeg;filename=smoke.jpg"
	rm -f "$image"
	if [[ "$STATUS" == "503" && "$BODY" == *QUEUE_UNAVAILABLE* ]]; then
		rm -f "$jar"
		printf 'skip  %s: the API says the scan queue is unavailable\n' "$name"
		return 0
	fi
	if ! expect_status "$name" 202; then
		rm -f "$jar"
		return 0
	fi
	scan_id="$(json_field id)"
	if [[ -z "$scan_id" ]]; then
		rm -f "$jar"
		fail "$name" "no scan id in the answer"
		return 0
	fi
	name="GET /scans/$scan_id"
	deadline=$((SECONDS + 60))
	while :; do
		fetch GET "$API_URL/scans/$scan_id" -b "$jar"
		if ! expect_status "$name" 200; then
			break
		fi
		state="$(json_field status)"
		case "$state" in
		done)
			pass "$name: done ($(json_field outcome))"
			break
			;;
		failed)
			if [[ "$(json_field error_code)" == "MODEL_UNAVAILABLE" ]]; then
				printf 'skip  %s: the API says the pipeline engine is unavailable (MODEL_UNAVAILABLE)\n' "$name"
			else
				fail "$name" "the scan failed: $(json_field error_code)"
			fi
			break
			;;
		queued | running)
			if ((SECONDS >= deadline)); then
				fail "$name" "still $state after 60 s"
				break
			fi
			sleep 2
			;;
		*)
			fail "$name" "unexpected status: $state"
			break
			;;
		esac
	done
	rm -f "$jar"
}

scan_checks() {
	rain_check
	trial_scan
}

mode=""
if [[ $read_only == 1 ]]; then
	mode=" (read-only)"
fi
printf 'smoke: site %s, api %s%s\n' "$SITE_URL" "$API_URL" "$mode"
web_checks
api_checks
write_checks
scan_checks

printf 'smoke: %d ok, %d failed\n' "$passed" "$failed"
[[ $failed == 0 ]]
