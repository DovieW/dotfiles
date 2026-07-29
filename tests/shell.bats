#!/usr/bin/env bats

@test "mbash runs non-interactively without the full bashrc" {
  run "$BATS_TEST_DIRNAME/../config/shell/mbash" -lc 'printf "%s" "$REPOS"'
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/repos" ]
}

@test "shell startup files do not persist a Bitwarden session" {
  run grep -R -E 'export[[:space:]]+BW_SESSION|BW_SESSION=' "$BATS_TEST_DIRNAME/../config/shell"
  [ "$status" -eq 1 ]
}
