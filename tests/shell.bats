#!/usr/bin/env bats

@test "mbash runs non-interactively without the full bashrc" {
  run env DOTFILES_ROOT="$BATS_TEST_DIRNAME/.." \
    "$BATS_TEST_DIRNAME/../config/shell/mbash" -lc 'printf "%s" "$REPOS"'
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/repos" ]
}

@test "shell startup files do not persist a Bitwarden session" {
  run grep -R -E 'export[[:space:]]+BW_SESSION|BW_SESSION=' "$BATS_TEST_DIRNAME/../config/shell"
  [ "$status" -eq 1 ]
}

@test "Codex installer recognizes the pinned standalone release" {
  release="$(python3 -c 'import json; print(json.load(open("'"$BATS_TEST_DIRNAME"'/../packages/codex.yml"))["release"])')"
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

@test "Codex installer check does not download when the CLI is missing" {
  fake_home="$BATS_TEST_TMPDIR/missing-codex-home"
  mkdir -p "$fake_home"

  run env -u CODEX_HOME -u CODEX_INSTALL_DIR HOME="$fake_home" \
    "$BATS_TEST_DIRNAME/../scripts/install-codex" --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"Codex standalone CLI is missing"* ]]
}

@test "Codex installer refuses implicit version changes" {
  fake_home="$BATS_TEST_TMPDIR/drifted-codex-home"
  fake_release="$fake_home/.codex/packages/standalone/releases/0.0.0/bin"
  mkdir -p "$fake_release" "$fake_home/.local/bin"
  printf '#!/bin/sh\nprintf "codex-cli 0.0.0\\n"\n' >"$fake_release/codex"
  chmod +x "$fake_release/codex"
  ln -s "$fake_release/codex" "$fake_home/.local/bin/codex"

  run env -u CODEX_HOME -u CODEX_INSTALL_DIR HOME="$fake_home" \
    "$BATS_TEST_DIRNAME/../scripts/install-codex" --ensure
  [ "$status" -eq 1 ]
  [[ "$output" == *"Review packages/codex.yml, then run: dot codex update"* ]]
}
