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
