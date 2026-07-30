# shellcheck shell=bash
# Shared interactive shell settings. Keep this file valid in both Bash and Zsh.

export REPOS="${REPOS:-$HOME/repos}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export VP_HOME="${VP_HOME:-$HOME/.vite-plus}"
export CLICOLOR=1

dot_fzf_config="${XDG_CONFIG_HOME}/fzf/fzfrc"
if [ -r "$dot_fzf_config" ]; then
  export FZF_DEFAULT_OPTS_FILE="$dot_fzf_config"
elif [ -n "${DOTFILES_ROOT:-}" ] && [ -r "$DOTFILES_ROOT/config/fzf/fzfrc" ]; then
  export FZF_DEFAULT_OPTS_FILE="$DOTFILES_ROOT/config/fzf/fzfrc"
fi
unset dot_fzf_config

# The common file owns appearance; each picker owns its geometry and preview.
export FZF_CTRL_T_OPTS="--height=75% --layout=reverse --input-label=' Files ' --list-label=' Results ' --preview-label=' Preview ' --prompt='Find › ' --preview='dot-fzf-preview {}' --preview-window='right,50%,border-left,<50(down,45%,border-top)' --bind='ctrl-/:toggle-preview'"
export FZF_ALT_C_OPTS="--height=65% --layout=reverse --input-label=' Directories ' --list-label=' Results ' --preview-label=' Preview ' --prompt='Go › ' --preview='dot-fzf-preview {}' --preview-window='right,50%,border-left,<50(down,45%,border-top)' --bind='ctrl-/:toggle-preview'"
export FZF_CTRL_R_OPTS="--height=60% --layout=reverse --input-label=' History ' --list-label=' Entries ' --prompt='Recall › '"

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
dot_path_prepend "$VP_HOME/bin"
dot_path_prepend "/home/linuxbrew/.linuxbrew/bin"
export PATH

if command -v nvim >/dev/null 2>&1; then
  export EDITOR=nvim VISUAL=nvim FCEDIT=nvim
elif command -v vim >/dev/null 2>&1; then
  export EDITOR=vim VISUAL=vim FCEDIT=vim
else
  export EDITOR=nano VISUAL=nano FCEDIT=nano
fi

for dot_bw_socket in \
  "$HOME/.bitwarden-ssh-agent.sock" \
  "$HOME/snap/bitwarden/current/.bitwarden-ssh-agent.sock"
do
  if [ -S "$dot_bw_socket" ]; then
    export SSH_AUTH_SOCK="$dot_bw_socket"
    break
  fi
done
unset dot_bw_socket

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
  host="$(
    awk '/^Host / {for (i=2;i<=NF;i++) if ($i !~ /[*?!]/) print $i}' "$HOME/.ssh/config" 2>/dev/null \
      | fzf --height=55% --layout=reverse \
          --input-label=' SSH hosts ' --list-label=' Hosts ' --prompt='Connect › '
  )"
  [ -n "$host" ] && command ssh "$host"
}
