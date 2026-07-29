# shellcheck shell=bash

dot_path_prepend() {
  [ -n "${1:-}" ] || return 0
  case ":$PATH:" in
    *":$1:"*) ;;
    *) PATH="$1${PATH:+:$PATH}" ;;
  esac
}

dot_path_prepend "$HOME/.local/bin"
dot_path_prepend "$HOME/bin"
dot_path_prepend "$HOME/.cargo/bin"
dot_path_prepend "$HOME/go/bin"
dot_path_prepend "$HOME/.bun/bin"
dot_path_prepend "$HOME/.vite-plus/bin"
dot_path_prepend "/home/linuxbrew/.linuxbrew/bin"
export PATH

export REPOS="${REPOS:-$HOME/repos}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export EDITOR="${EDITOR:-vim}"
export VISUAL="${VISUAL:-$EDITOR}"
export FCEDIT="${FCEDIT:-$EDITOR}"

alias l='ls -CF'
alias la='ls -A'
alias ll='ls -alF'
alias g='git'
alias repos='cd "$REPOS"'
