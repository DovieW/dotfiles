#!/usr/bin/env bash
set -euo pipefail

if ! command -v bw >/dev/null 2>&1; then
	printf 'Bitwarden CLI (bw) is not installed. Run setup-wsl.sh --with-bitwarden first.\n' >&2
	exit 1
fi

status="$(bw status 2>/dev/null | sed -n 's/.*"status":"\([^"]*\)".*/\1/p' || true)"
if [ "$status" = "unauthenticated" ] || [ -z "$status" ]; then
	bw login
fi

session="$(bw unlock --raw)"
if [ -z "$session" ]; then
	printf 'Bitwarden unlock did not return a session token.\n' >&2
	exit 1
fi

printf 'export BW_SESSION=%q\n' "$session"
