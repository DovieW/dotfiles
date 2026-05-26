#!/usr/bin/env bash
set -euo pipefail

dry_run=0
profile=""
with_bitwarden=0
with_private=0

for arg in "$@"; do
	case "$arg" in
		--wsl-core) profile="wsl-core" ;;
		--dotfiles-only) profile="dotfiles-only" ;;
		--all-safe) profile="all-safe" ;;
		--with-bitwarden) with_bitwarden=1 ;;
		--with-private) with_private=1 ;;
		--dry-run) dry_run=1 ;;
		*) printf 'Unknown argument: %s\n' "$arg" >&2; exit 2 ;;
	esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run() {
	printf '+ %s\n' "$*"
	if [ "$dry_run" -eq 0 ]; then
		"$@"
	fi
}

has() {
	command -v "$1" >/dev/null 2>&1
}

confirm() {
	local prompt="$1"
	if has gum; then
		gum confirm "$prompt"
		return
	fi
	printf '%s [y/N] ' "$prompt"
	read -r answer
	case "$answer" in
		y|Y|yes|YES) return 0 ;;
		*) return 1 ;;
	esac
}

install_apt() {
	if ! has apt-get; then
		printf 'apt-get not found; skipping apt package install.\n' >&2
		return
	fi
	run sudo apt-get update
	run sudo apt-get install -y "$@"
}

ensure_command() {
	local command_name="$1"
	shift
	if has "$command_name"; then
		return
	fi
	if [ "$#" -gt 0 ]; then
		install_apt "$@"
	fi
}

ensure_bitwarden() {
	if has bw; then
		return
	fi
	printf 'Bitwarden CLI is required for the selected secret-backed module.\n'
	printf 'Install bw using your preferred Bitwarden CLI method, then rerun this script.\n'
	return 1
}

apply_dotfiles() {
	ensure_command chezmoi chezmoi || true
	if ! has chezmoi; then
		printf 'chezmoi is not installed. Install it from https://www.chezmoi.io/install/ and rerun.\n' >&2
		return 1
	fi
	run chezmoi apply --source "$repo_root"
}

install_shell_tools() {
	install_apt git curl fzf tmux zoxide ripgrep fd-find bat jq
}

wire_shell_rc() {
	local line='[ -f "$HOME/.config/dovie-shell/shell.sh" ] && . "$HOME/.config/dovie-shell/shell.sh"'
	for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
		touch "$rc"
		if ! grep -Fqx "$line" "$rc"; then
			printf '%s\n' "$line" >> "$rc"
			printf 'Added dovie shell source line to %s\n' "$rc"
		fi
	done
}

run_wsl_core() {
	install_shell_tools
	apply_dotfiles
	wire_shell_rc
}

if [ "$profile" = "wsl-core" ] || [ "$profile" = "all-safe" ]; then
	run_wsl_core
elif [ "$profile" = "dotfiles-only" ]; then
	apply_dotfiles
else
	if confirm 'Install/update common WSL shell tools?'; then
		install_shell_tools
	fi
	if confirm 'Apply chezmoi dotfiles?'; then
		apply_dotfiles
	fi
	if confirm 'Wire shell startup files to source dovie shell config?'; then
		wire_shell_rc
	fi
fi

if [ "$with_bitwarden" -eq 1 ]; then
	ensure_bitwarden
	printf 'Run this to unlock into the current shell:\n'
	printf '  eval "$(%q/scripts/unlock-bitwarden.sh)"\n' "$repo_root"
fi

if [ "$with_private" -eq 1 ]; then
	ensure_command gh gh || true
	printf 'Private setup uses the existing DovieW/files repo as the workbench/archive.\n'
	printf 'Clone it manually where desired: gh repo clone DovieW/files ~/repos/files\n'
fi
