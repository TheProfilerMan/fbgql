#!/usr/bin/env bash
#
# One-command bootstrap + run for local/host use (a machine with a browser).
#
#   ./run.sh                       # scrape PAGE (default ronaldo), logged out
#   ./run.sh <page> 30             # page + post count
#   ./run.sh doctor                # check doc_ids still resolve
#   AUTH=1 ./run.sh                # scrape with a real session (mints cookies if needed)
#   ./run.sh login                 # just mint/refresh cookies, don't scrape
#   ./run.sh capture               # record CURRENT doc_ids+variables from a browser
#                                  #   (use when a run reports a stale-query error)
#
# Scraping is ANONYMOUS by default: no login, no cookies, no browser. Set AUTH=1 only
# when you need login-gated content (private groups, age/geo-restricted posts).
#
# It will, on first run: pick Python 3.11+, create .venv, install the package.
#
# Override anything via env, e.g.:
#   PAGE=ronaldo POSTS=20 PROFILE=default ENGINE=threads OUT=out/result.json ./run.sh
#
# NOTE: AUTH=1, `login`, and `capture` need a display for the browser step. The default
# anonymous path does not, so it works fine in containers.
set -euo pipefail
cd "$(dirname "$0")"

# ---- config (env-overridable) ------------------------------------------------
CMD="scrape"
case "${1:-}" in
  login|doctor|capture) CMD="$1"; shift ;;
  scrape) shift ;;
esac
# Positional PAGE/POSTS are optional shortcuts; anything starting with '-' (e.g.
# --posts 1, --profile tops_only) is forwarded verbatim to the fbgql CLI and wins
# over the positionals/env below.
POSITIONAL=()
PASSTHROUGH=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -*) PASSTHROUGH+=("$1"); shift
        # attach a following value if the next token isn't itself a flag
        if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then PASSTHROUGH+=("$1"); shift; fi ;;
    *)  POSITIONAL+=("$1"); shift ;;
  esac
done
PAGE="${POSITIONAL[0]:-${PAGE:-ronaldo}}"
POSTS="${POSITIONAL[1]:-${POSTS:-20}}"
PROFILE="${PROFILE:-default}"
ENGINE="${ENGINE:-threads}"
COOKIES="${COOKIES:-cookies.json}"
# Empty => anonymous (default). Set AUTH=1 to scrape with a real session.
AUTH="${AUTH:-}"
OUT="${OUT:-out/result.json}"
PROXY="${PROXY:-}"
# Reply policy: fetch replies only when a post's FB comment_count < REPLY_CAP.
# REPLY_CAP=0 => tops only (no reply requests). Unset => use the profile's preset.
REPLY_CAP="${REPLY_CAP:-}"

# ---- pick a Python 3.11+ interpreter -----------------------------------------
pick_python() {
  for c in "${PYTHON:-}" python3.13 python3.12 python3.11 \
           /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 python3; do
    [ -z "$c" ] && continue
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}

# ---- venv + install (first run only) -----------------------------------------
if [ ! -d .venv ]; then
  PY="$(pick_python)" || {
    echo "ERROR: need Python 3.11+. Install it, e.g.:  brew install python@3.12" >&2
    exit 1
  }
  echo "Creating .venv with $PY …"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -c 'import fbgql' >/dev/null 2>&1 || {
  echo "Installing fbgql …"
  pip install -q --upgrade pip
  pip install -q -e .
}

# ---- cookies: mint only if missing/expired -----------------------------------
cookies_valid() {
  [ -f "$COOKIES" ] || return 1
  python - "$COOKIES" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    if isinstance(d, dict) and isinstance(d.get("cookies"), dict):
        d = d["cookies"]
    if isinstance(d, list):
        d = {c["name"]: c["value"] for c in d}
    sys.exit(0 if d.get("c_user") and d.get("xs") else 1)
except Exception:
    sys.exit(1)
PY
}

mint() {
  echo "No valid cookies at '$COOKIES' — opening a browser to log in…"
  python -c 'import selenium' >/dev/null 2>&1 || pip install -q -e ".[mint]"
  fbgql mint-session --out "$COOKIES"
}

# Cookies are only needed for AUTH=1 scraping, `login`, and `capture`. The default
# anonymous path never opens a browser.
if [ -n "$AUTH" ] || [ "$CMD" = "login" ] || [ "$CMD" = "capture" ]; then
  cookies_valid || mint
fi

[ "$CMD" = "login" ] && { echo "Cookies ready at $COOKIES"; exit 0; }

if [ "$CMD" = "doctor" ]; then
  args=(doctor --page "$PAGE")
  [ -n "$AUTH" ] && args+=(--cookies "$COOKIES")
  [ -n "$PROXY" ] && args+=(--proxy "$PROXY")
  exec fbgql "${args[@]}"
fi

if [ "$CMD" = "capture" ]; then
  python -c 'import selenium' >/dev/null 2>&1 || pip install -q -e ".[mint]"
  echo "Capturing live GraphQL queries for $PAGE (a browser will open)…"
  exec fbgql capture --page "$PAGE" --cookies "$COOKIES" --out captured_queries.json
fi

# ---- scrape ------------------------------------------------------------------
mkdir -p "$(dirname "$OUT")"
echo "Scraping $PAGE — $POSTS posts, profile=$PROFILE, engine=$ENGINE," \
     "access=$([ -n "$AUTH" ] && echo authenticated || echo anonymous)"
args=(scrape --page "$PAGE" --posts "$POSTS" --profile "$PROFILE" --engine "$ENGINE"
      --out "$OUT")
[ -n "$AUTH" ] && args+=(--cookies "$COOKIES")
[ -n "$PROXY" ] && args+=(--proxy "$PROXY")
[ -n "$REPLY_CAP" ] && args+=(--reply-cap "$REPLY_CAP")
# Forward any --flags given on the command line (they override the above).
[ "${#PASSTHROUGH[@]}" -gt 0 ] && args+=("${PASSTHROUGH[@]}")
exec fbgql "${args[@]}"
