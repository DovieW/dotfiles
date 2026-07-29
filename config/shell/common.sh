# shellcheck shell=bash
# Shared interactive shell settings. Keep this file valid in both Bash and Zsh.

export REPOS="${REPOS:-$HOME/repos}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export CLICOLOR=1

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

if command -v nvim >/dev/null 2>&1; then
  export EDITOR=nvim VISUAL=nvim FCEDIT=nvim
elif command -v vim >/dev/null 2>&1; then
  export EDITOR=vim VISUAL=vim FCEDIT=vim
else
  export EDITOR=nano VISUAL=nano FCEDIT=nano
fi

if [ -S "$HOME/.bitwarden-ssh-agent.sock" ]; then
  export SSH_AUTH_SOCK="$HOME/.bitwarden-ssh-agent.sock"
fi

alias g='git'
alias t='tmux'
alias tls='tmux ls'
alias ta='tmux attach'
alias repos='cd "$REPOS"'
alias c-='cd -'
alias c.='cd ..'
alias c..='cd ../..'
alias c...='cd ../../..'

if command -v eza >/dev/null 2>&1; then
  alias ls='eza'
  alias l='eza --oneline --classify --color=auto --icons=auto --all --group-directories-first'
  alias ll='eza --long --all --group-directories-first --git --icons=auto'
else
  alias l='ls -1AF --color=auto'
  alias ll='ls -hlAF --color=auto'
fi

if command -v bat >/dev/null 2>&1; then
  alias cat='bat --no-paging --plain'
fi

groot() {
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || return
  cd "$root" || return
}

v() {
  "${V_EDITOR:-$EDITOR}" "$@"
}

mkcd() {
  mkdir -p -- "$1" && cd -- "$1" || return
}

dot_ssh_select() {
  if [ "$#" -gt 0 ]; then
    command ssh "$@"
    return
  fi
  if ! command -v fzf >/dev/null 2>&1; then
    echo "fzf is required for interactive SSH host selection." >&2
    return 1
  fi
  local host
  host="$(awk '/^Host / {for (i=2;i<=NF;i++) if ($i !~ /[*?!]/) print $i}' "$HOME/.ssh/config" 2>/dev/null | fzf --prompt='SSH host: ')"
  [ -n "$host" ] && command ssh "$host"
}
