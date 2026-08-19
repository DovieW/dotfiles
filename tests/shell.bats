#!/usr/bin/env bats

@test "mbash runs non-interactively without the full bashrc" {
  run env DOTFILES_ROOT="$BATS_TEST_DIRNAME/.." \
    "$BATS_TEST_DIRNAME/../config/shell/mbash" -lc 'printf "%s" "$REPOS"'
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/repos" ]
}

@test "mbash prompt is visibly labeled without dynamic work" {
  run env DOTFILES_ROOT="$BATS_TEST_DIRNAME/.." \
    bash --noprofile --rcfile "$BATS_TEST_DIRNAME/../config/shell/minimal-bashrc" \
    -ic 'printf "%s" "$PS1"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"[mbash]"* ]]
  run grep -E 'command -v|git |\$\(' "$BATS_TEST_DIRNAME/../config/shell/minimal-bashrc"
  [ "$status" -eq 1 ]
}

@test "full Bash prompt shows mode path Git context and exit status" {
  run env DOTFILES_ROOT="$BATS_TEST_DIRNAME/.." \
    bash --noprofile --rcfile "$BATS_TEST_DIRNAME/../config/shell/bashrc" \
    -ic '__dot_bash_prompt 7; printf "%s" "$PS1"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"bash"* ]]
  [[ "$output" == *'\w'* ]]
  [[ "$output" == *"git:"* ]]
  [[ "$output" == *"[7]"* ]]
  [[ "$output" == *"❯"* ]]
}

@test "shell startup files do not persist a Bitwarden session" {
  run grep -R -E 'export[[:space:]]+BW_SESSION|BW_SESSION=' "$BATS_TEST_DIRNAME/../config/shell"
  [ "$status" -eq 1 ]
}

@test "interactive shells discard automation Git pager overrides" {
  run env GIT_PAGER=cat bash --noprofile --norc -ic \
    'source "$1"; printf "RESULT=%s" "${GIT_PAGER-unset}"' bash \
    "$BATS_TEST_DIRNAME/../config/shell/common.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RESULT=unset" ]]

  run env GIT_PAGER=cat bash --noprofile --norc -c \
    'source "$1"; printf "%s" "$GIT_PAGER"' bash \
    "$BATS_TEST_DIRNAME/../config/shell/common.sh"
  [ "$status" -eq 0 ]
  [ "$output" = "cat" ]
}

@test "Git and tmux keep Delta available to interactive users" {
  run grep -F $'\tdiff = delta' "$BATS_TEST_DIRNAME/../config/git/delta.gitconfig"
  [ "$status" -eq 0 ]
  run grep -F 'set-environment -gu GIT_PAGER' "$BATS_TEST_DIRNAME/../config/tmux/tmux.conf"
  [ "$status" -eq 0 ]
}

@test "cat renders one Markdown file with Glow and preserves Bat otherwise" {
  fake_bin="$BATS_TEST_TMPDIR/cat-bin"
  call_log="$BATS_TEST_TMPDIR/cat-calls"
  markdown="$BATS_TEST_TMPDIR/notes.md"
  text_file="$BATS_TEST_TMPDIR/notes.txt"
  mkdir -p "$fake_bin"
  printf '# heading\n' >"$markdown"
  printf 'plain text\n' >"$text_file"
  printf '%s\n' \
    '#!/bin/sh' \
    'printf "glow\\n" >>"$DOT_TEST_CAT_LOG"' \
    'printf "arg=%s\\n" "$@" >>"$DOT_TEST_CAT_LOG"' >"$fake_bin/glow"
  printf '%s\n' \
    '#!/bin/sh' \
    'printf "bat\\n" >>"$DOT_TEST_CAT_LOG"' \
    'printf "arg=%s\\n" "$@" >>"$DOT_TEST_CAT_LOG"' >"$fake_bin/bat"
  chmod +x "$fake_bin/glow" "$fake_bin/bat"

  run env PATH="$fake_bin:/usr/bin:/bin" DOT_TEST_CAT_LOG="$call_log" \
    bash --noprofile --norc -c \
    'source "$1"; PATH="$4:/usr/bin:/bin"; cat "$2"; cat "$3"; cat "$2" "$3"' bash \
    "$BATS_TEST_DIRNAME/../config/shell/common.sh" "$markdown" "$text_file" "$fake_bin"
  [ "$status" -eq 0 ]
  [ "$(grep -c '^glow$' "$call_log")" -eq 1 ]
  [ "$(grep -c '^bat$' "$call_log")" -eq 2 ]
  grep -Fxq "arg=--" "$call_log"
  grep -Fxq "arg=$markdown" "$call_log"
  grep -Fxq "arg=--no-paging" "$call_log"
  grep -Fxq "arg=--plain" "$call_log"
  grep -Fxq "arg=$text_file" "$call_log"
}

@test "shared fzf configuration contains presentation options only" {
  config="$BATS_TEST_DIRNAME/../config/fzf/fzfrc"
  run grep -E -- '--(height|preview|prompt|delimiter|multi)(=|$)' "$config"
  [ "$status" -eq 1 ]
  run grep -F -- '--style=full:rounded' "$config"
  [ "$status" -eq 0 ]
  run grep -F -- '--color=fg:#c9d1d9,bg:#07090d' "$config"
  [ "$status" -eq 0 ]
}

@test "fzf preview renders files and directories without executing them" {
  preview="$BATS_TEST_DIRNAME/../config/fzf/preview"
  sample="$BATS_TEST_TMPDIR/fzf-preview"
  marker="$BATS_TEST_TMPDIR/should-not-exist"
  mkdir -p "$sample/directory"
  printf '#!/bin/sh\ntouch "%s"\n' "$marker" >"$sample/example.sh"
  chmod +x "$sample/example.sh"
  printf 'inside\n' >"$sample/directory/child.txt"

  run env PATH="/usr/bin:/bin" "$preview" "$sample/example.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *'touch '* ]]
  [ ! -e "$marker" ]

  run env PATH="/usr/bin:/bin" "$preview" "$sample/directory"
  [ "$status" -eq 0 ]
  [[ "$output" == *'child.txt'* ]]
}

@test "clip selects the native Wayland clipboard backend" {
  fake_bin="$BATS_TEST_TMPDIR/clip-bin"
  clipboard="$BATS_TEST_TMPDIR/clipboard"
  mkdir -p "$fake_bin"
  printf '%s\n' \
    '#!/bin/sh' \
    'cat >"$DOT_TEST_CLIPBOARD"' >"$fake_bin/wl-copy"
  chmod +x "$fake_bin/wl-copy"

  run env PATH="$fake_bin:$PATH" WAYLAND_DISPLAY=wayland-0 \
    DOT_TEST_CLIPBOARD="$clipboard" \
    bash -c 'printf %s clipboard-text | "$1"' bash \
    "$BATS_TEST_DIRNAME/../config/shell/clip"
  [ "$status" -eq 0 ]
  [ "$(cat "$clipboard")" = "clipboard-text" ]
}

@test "cclip concatenates files through clip" {
  fake_bin="$BATS_TEST_TMPDIR/cclip-bin"
  clipboard="$BATS_TEST_TMPDIR/cclip-output"
  first="$BATS_TEST_TMPDIR/first"
  second="$BATS_TEST_TMPDIR/second"
  mkdir -p "$fake_bin"
  printf '#!/bin/sh\ncat >\"$DOT_TEST_CLIPBOARD\"\n' >"$fake_bin/clip"
  chmod +x "$fake_bin/clip"
  printf first >"$first"
  printf second >"$second"

  run env PATH="$fake_bin:$PATH" CLIP_COMMAND="$fake_bin/clip" \
    DOT_TEST_CLIPBOARD="$clipboard" \
    "$BATS_TEST_DIRNAME/../config/shell/cclip" "$first" "$second"
  [ "$status" -eq 0 ]
  [ "$(cat "$clipboard")" = "firstsecond" ]
}

@test "dot-rdp routes F5 launch files through the managed Remmina flow" {
  fake_bin="$BATS_TEST_TMPDIR/rdp-bin"
  captured_argv="$BATS_TEST_TMPDIR/rdp-argv"
  rdp_file="$BATS_TEST_TMPDIR/f5-launch.rdp"
  mkdir -p "$fake_bin"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "%s\n" "$@" >"$DOT_TEST_RDP_ARGV"' >"$fake_bin/dot-remmina-f5"
  chmod +x "$fake_bin/dot-remmina-f5"
  printf '%s\r\n' \
    'full address:s:remote.example.test' \
    'enablecredsspsupport:i:0' \
    'gatewayaccesstoken:s:one-time-token' >"$rdp_file"

  run env PATH="$fake_bin:$PATH" \
    DOT_TEST_RDP_ARGV="$captured_argv" \
    DOT_REMMINA_F5_HELPER="$fake_bin/dot-remmina-f5" \
    "$BATS_TEST_DIRNAME/../config/rdp/dot-rdp" "$rdp_file"

  [ "$status" -eq 0 ]
  [ "$(cat "$captured_argv")" = "$rdp_file" ]
}

@test "dot-remmina-f5 builds a private native-resolution fullscreen profile" {
  fake_bin="$BATS_TEST_TMPDIR/remmina-bin"
  fake_configure="$BATS_TEST_TMPDIR/configure-remmina"
  captured_profile="$BATS_TEST_TMPDIR/remmina-profile"
  runtime_dir="$BATS_TEST_TMPDIR/runtime"
  rdp_file="$BATS_TEST_TMPDIR/f5-launch.rdp"
  mkdir -p "$fake_bin" "$runtime_dir"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'cp "$2" "$DOT_TEST_REMMINA_PROFILE"' >"$fake_bin/remmina"
  chmod +x "$fake_bin/remmina"
  printf '#!/bin/sh\nexit 0\n' >"$fake_configure"
  chmod +x "$fake_configure"
  printf '%s\r\n' \
    'full address:s:remote.example.test' \
    'gatewayhostname:s:gateway.example.test' \
    'gatewayaccesstoken:s:one-time-token' \
    'authentication level:i:0' >"$rdp_file"

  run env PATH="$fake_bin:$PATH" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DOT_TEST_REMMINA_PROFILE="$captured_profile" \
    DOT_REMMINA_CONFIGURE="$fake_configure" \
    "$BATS_TEST_DIRNAME/../config/rdp/dot-remmina-f5" "$rdp_file"

  [ "$status" -eq 0 ]
  grep -Fxq "server=remote.example.test" "$captured_profile"
  grep -Fxq "gateway_server=gateway.example.test" "$captured_profile"
  grep -Fxq "gatewayaccesstoken=one-time-token" "$captured_profile"
  grep -Fxq "resolution_mode=0" "$captured_profile"
  grep -Fxq "resolution_width=2880" "$captured_profile"
  grep -Fxq "resolution_height=1800" "$captured_profile"
  grep -Fxq "scale=1" "$captured_profile"
  grep -Fxq "viewmode=4" "$captured_profile"
  grep -Fxq "quality=9" "$captured_profile"
  grep -Fxq "cert_ignore=0" "$captured_profile"
  [ ! -e "$runtime_dir/dotfiles-remmina-$(id -u)/f5-current.remmina" ]
}

@test "Codex installer accepts a managed stable-channel release" {
  release="9.8.7"
  fake_home="$BATS_TEST_TMPDIR/codex-home"
  fake_release="$fake_home/.codex/packages/standalone/releases/$release/bin"
  mkdir -p "$fake_release" "$fake_home/.local/bin"
  printf '#!/bin/sh\nprintf "codex-cli %s\\n" "%s"\n' "$release" "$release" >"$fake_release/codex"
  chmod +x "$fake_release/codex"
  ln -s "$fake_release/codex" "$fake_home/.local/bin/codex"

  run env -u CODEX_HOME -u CODEX_INSTALL_DIR HOME="$fake_home" \
    "$BATS_TEST_DIRNAME/../scripts/install-codex" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"Codex CLI $release is installed"* ]]
}

@test "transcribe installer downloads and verifies the pinned public release" {
  fake_home="$BATS_TEST_TMPDIR/transcribe-home"
  fake_release="$BATS_TEST_TMPDIR/transcribe-linux-x64"
  mkdir -p "$fake_home"
  printf '#!/bin/sh\nprintf "transcribe 2.0.0\\n"\n' >"$fake_release"
  chmod +x "$fake_release"
  release_hash="$(sha256sum "$fake_release" | cut -d' ' -f1)"

  run env HOME="$fake_home" \
    XDG_DATA_HOME="$fake_home/data" \
    XDG_BIN_HOME="$fake_home/bin" \
    TRANSCRIBE_RELEASE_URL="file://$fake_release" \
    TRANSCRIBE_EXPECTED_SHA256="$release_hash" \
    "$BATS_TEST_DIRNAME/../scripts/install-transcribe" --install
  [ "$status" -eq 0 ]
  [[ "$output" == *"DovieW/transcribe-cli"* ]]
  [ -L "$fake_home/bin/transcribe" ]

  run env HOME="$fake_home" \
    XDG_DATA_HOME="$fake_home/data" \
    XDG_BIN_HOME="$fake_home/bin" \
    TRANSCRIBE_EXPECTED_SHA256="$release_hash" \
    "$BATS_TEST_DIRNAME/../scripts/install-transcribe" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"public release is current"* ]]
}

@test "Codex installer check does not download when the CLI is missing" {
  fake_home="$BATS_TEST_TMPDIR/missing-codex-home"
  mkdir -p "$fake_home"

  run env -u CODEX_HOME -u CODEX_INSTALL_DIR HOME="$fake_home" \
    "$BATS_TEST_DIRNAME/../scripts/install-codex" --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"Codex standalone CLI is missing"* ]]
}

@test "Codex ensure accepts an existing managed release without downloading" {
  fake_home="$BATS_TEST_TMPDIR/drifted-codex-home"
  fake_release="$fake_home/.codex/packages/standalone/releases/0.0.0/bin"
  mkdir -p "$fake_release" "$fake_home/.local/bin"
  printf '#!/bin/sh\nprintf "codex-cli 0.0.0\\n"\n' >"$fake_release/codex"
  chmod +x "$fake_release/codex"
  ln -s "$fake_release/codex" "$fake_home/.local/bin/codex"

  run env -u CODEX_HOME -u CODEX_INSTALL_DIR HOME="$fake_home" \
    "$BATS_TEST_DIRNAME/../scripts/install-codex" --ensure
  [ "$status" -eq 0 ]
  [[ "$output" == *"managed stable channel"* ]]
}

@test "Vite+ installer accepts a managed stable-channel release" {
  release="9.8.7"
  fake_home="$BATS_TEST_TMPDIR/vite-plus-home"
  fake_release="$fake_home/.vite-plus/$release/bin"
  mkdir -p "$fake_release" "$fake_home/.vite-plus/bin"
  printf '#!/bin/sh\nprintf "vp v%s\\n" "%s"\n' "$release" "$release" >"$fake_release/vp"
  chmod +x "$fake_release/vp"
  ln -s "$fake_home/.vite-plus/$release" "$fake_home/.vite-plus/current"
  ln -s "$fake_release/vp" "$fake_home/.vite-plus/bin/vp"
  printf '#!/bin/sh\n' >"$fake_home/.vite-plus/env"

  run env HOME="$fake_home" VP_HOME="$fake_home/.vite-plus" \
    "$BATS_TEST_DIRNAME/../scripts/install-vite-plus" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"Vite+ $release is installed from the managed stable channel"* ]]
}

@test "sudo-rs become plugin recognizes the wrapped PAM prompt" {
  fake_sudo="$BATS_TEST_TMPDIR/sudo-rs"
  playbook="$BATS_TEST_TMPDIR/sudo-rs.yml"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'prompt=' \
    'while (($#)); do' \
    '  case "$1" in' \
    '    -p|--prompt) prompt="$2"; shift 2 ;;' \
    '    -u|--user) shift 2 ;;' \
    '    -n|--non-interactive) echo "sudo-rs rejected interactive authentication" >&2; exit 1 ;;' \
    '    -H|-S|--stdin) shift ;;' \
    '    *) break ;;' \
    '  esac' \
    'done' \
    'printf "[sudo: %s] Password:" "$prompt" >&2' \
    'IFS= read -r password' \
    '[[ "$password" == test-password ]]' \
    'exec "$@"' >"$fake_sudo"
  chmod +x "$fake_sudo"
  printf '%s\n' \
    '---' \
    '- name: Exercise sudo-rs become handshake' \
    '  hosts: localhost' \
    '  gather_facts: false' \
    '  vars:' \
    '    ansible_become_password: test-password' \
    '  tasks:' \
    '    - name: Run through the emulated sudo-rs prompt' \
    '      ansible.builtin.command: id -u' \
    '      become: true' \
    '      changed_when: false' >"$playbook"

  run bash -c '
    ANSIBLE_CONFIG="$1/../ansible/ansible.cfg" \
      ANSIBLE_BECOME_PLUGINS="$1/../ansible/become_plugins" \
      ANSIBLE_BECOME_EXE="$2" \
      ANSIBLE_LOCAL_TEMP="$3" \
      ansible-playbook "$4" -i localhost, -c local --become-method sudo_rs
  ' bash "$BATS_TEST_DIRNAME" "$fake_sudo" "$BATS_TEST_TMPDIR/ansible-tmp" "$playbook"
  [ "$status" -eq 0 ]
  [[ "$output" == *"failed=0"* ]]
}
