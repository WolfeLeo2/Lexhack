#!/usr/bin/env bash
# Share $LEXHACK_DATA through Cloudflare R2 (rclone). Copies only; never deletes on either side.
#
#   scripts/sync.sh pull                  # get what the other person added
#   scripts/sync.sh push                  # upload what you added
#   scripts/sync.sh push --with-frontier  # also raw/frontier.db (ONLY the person who crawls; nobody else writes it)
#   scripts/sync.sh push --dry-run        # show what would be copied
#
# Safe to run both ways: caches are named by content hash, so two people's caches merge without overwriting.
# Don't sync while a pipeline job (crawl, parse, classify, llm_resolve) is running.
# Remote: $LEXHACK_R2 (default lexhack-data:lexhack-data = rclone remote "lexhack-data", bucket "lexhack-data").
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && export $(grep -E '^LEXHACK_DATA=' .env | xargs)
: "${LEXHACK_DATA:?LEXHACK_DATA not set (in .env or the environment)}"
REMOTE="${LEXHACK_R2:-lexhack-data:lexhack-data}"
DIR="${1:-}"; shift || true
EXTRA=(); FRONTIER=0
for a in "$@"; do [ "$a" = "--with-frontier" ] && FRONTIER=1 || EXTRA+=("$a"); done
FILTER=(--exclude "raw/frontier.db*" --exclude "*.pid" --exclude "raw/STOPPED.txt" --exclude "raw/*.out"
        --exclude "raw/*.log" --exclude ".DS_Store")
[ "$FRONTIER" = 1 ] && FILTER=(--include "raw/frontier.db" "${FILTER[@]}")
FLAGS=(--checksum --transfers 16 --checkers 32 --fast-list --progress "${FILTER[@]}" "${EXTRA[@]+"${EXTRA[@]}"}")
case "$DIR" in
  push) rclone copy "$LEXHACK_DATA" "$REMOTE" "${FLAGS[@]}" ;;
  pull) rclone copy "$REMOTE" "$LEXHACK_DATA" "${FLAGS[@]}" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
