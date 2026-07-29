#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if ! command -v pkg >/dev/null 2>&1; then
  echo "This bootstrap must run inside Termux." >&2
  exit 1
fi

pkg install -y git openssh python nodejs-lts zsh
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/bin/dot" \
  bootstrap --profile termux "$@"
