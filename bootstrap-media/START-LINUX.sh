#!/usr/bin/env bash
set -euo pipefail

media="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if grep -qi microsoft /proc/version 2>/dev/null; then
  printf '%s\n' 'Select a WSL profile:' '  1) Personal' '  2) Work'
  read -r -p 'Choice [1]: ' choice
  case "${choice:-1}" in
    1) profile=wsl-personal ;;
    2) profile=wsl-work ;;
    *) echo 'Invalid profile choice.' >&2; exit 2 ;;
  esac
else
  profile=
fi

cd "$media"
sha256sum --check SHA256SUMS
sudo apt-get update
sudo apt-get install -y ca-certificates git python3

destination="$HOME/repos/dotfiles"
if [[ -e "$destination" ]]; then
  if [[ ! -d "$destination/.git" ]] || [[ -n "$(git -C "$destination" status --porcelain)" ]]; then
    echo "$destination exists and is not a clean dotfiles checkout; it was not changed." >&2
    exit 1
  fi
  current_origin="$(git -C "$destination" remote get-url origin 2>/dev/null || true)"
  case "$current_origin" in
    git@github.com:DovieW/dotfiles.git | https://github.com/DovieW/dotfiles.git) ;;
    *) echo "$destination has an unexpected origin; it was not changed." >&2; exit 1 ;;
  esac
  git -C "$destination" fetch "$media/payload/dotfiles.bundle" master
  git -C "$destination" merge --ff-only FETCH_HEAD
else
  mkdir -p "$(dirname -- "$destination")"
  git clone "$media/payload/dotfiles.bundle" "$destination"
  git -C "$destination" remote remove origin 2>/dev/null || true
  git -C "$destination" remote add origin git@github.com:DovieW/dotfiles.git
fi

# The USB is the offline trust anchor, not a reason to physically shuttle every
# bootstrap fix. Prefer the current public master when GitHub is reachable and
# retain the verified bundle revision as an automatic offline fallback.
if git -C "$destination" fetch \
  https://github.com/DovieW/dotfiles.git master; then
  git -C "$destination" merge --ff-only FETCH_HEAD
  echo "Dotfiles updated from current GitHub master."
else
  echo "GitHub was unreachable; continuing from the verified USB bundle." >&2
fi

if [[ -z "$profile" ]]; then
  device="$(hostname | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+|-+$//g')"
  manifest="$destination/devices/$device.yml"
  if [[ -f "$manifest" ]]; then
    profile="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["profile"])' "$manifest")"
    echo "Recognized $device as profile $profile."
  else
    printf '%s\n' 'Select this Kubuntu computer type:' '  1) Laptop' '  2) Desktop'
    read -r -p 'Choice [1]: ' choice
    case "${choice:-1}" in
      1) profile=kubuntu-laptop ;;
      2) profile=kubuntu-desktop ;;
      *) echo 'Invalid profile choice.' >&2; exit 2 ;;
    esac
  fi
fi

exec "$destination/bin/dot" bootstrap --profile "$profile"
