"""Exercise the actual pre-push hook against a disposable local bare remote."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("gitleaks") or
                     Path("/home/linuxbrew/.linuxbrew/bin/gitleaks").is_file(),
                     "Gitleaks is not installed")
class PushSecretIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True, env=self.env)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True, env=self.env)
        self.git("config", "user.name", "Secret gate test")
        self.git("config", "user.email", "test@example.invalid")
        for relative in (".githooks/pre-push", "scripts/check-push-secrets", ".gitleaks.toml"):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.commit("initial")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "origin", "main")
        self.git("config", "core.hooksPath", str(self.repo / ".githooks"))
        # A deliberately fake provider-shaped token, assembled only at runtime.
        self.token = "gh" + "p_" + "6vN8bQ2mD9xK4rT7wY1aF5cH3jL0sE8zU9iP"

    def git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              check=check, capture_output=True, text=True)

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-q", "-m", message)

    def leak(self):
        (self.repo / "credential.txt").write_text("access_token = " + self.token + "\n")
        self.commit("synthetic secret fixture")

    def assert_blocked(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Push blocked", result.stderr)
        self.assertNotIn(self.token, result.stdout + result.stderr)

    def test_clean_existing_and_new_branch_pushes_succeed(self):
        (self.repo / "note.txt").write_text("ordinary configuration\n")
        self.commit("clean update")
        self.assertEqual(self.git("push", "origin", "main").returncode, 0)
        self.assertEqual(self.git("push", "origin", "HEAD:refs/heads/new-branch").returncode, 0)

    def test_secret_blocks_existing_branch_and_redacts_output(self):
        before = self.git("rev-parse", "origin/main").stdout.strip()
        self.leak()
        self.assert_blocked(self.git("push", "origin", "main", check=False))
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").stdout.split()[0], before)

    def test_deleted_secret_in_an_earlier_commit_still_blocks(self):
        self.leak()
        (self.repo / "credential.txt").unlink()
        self.commit("remove synthetic secret")
        self.assert_blocked(self.git("push", "origin", "main", check=False))

    def test_new_branch_and_annotated_tag_secrets_block(self):
        self.leak()
        self.assert_blocked(self.git("push", "origin", "HEAD:refs/heads/new-branch", check=False))
        self.git("tag", "-a", "test-tag", "-m", "tag fixture")
        self.assert_blocked(self.git("push", "origin", "refs/tags/test-tag", check=False))

    def test_multi_ref_push_checks_every_ref(self):
        self.git("branch", "clean")
        self.leak()
        self.assert_blocked(self.git("push", "origin", "clean", "main", check=False))
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/clean").stdout, "")

    def test_secret_in_commit_message_blocks(self):
        self.git("commit", "--allow-empty", "-m", "access_token = " + self.token)
        self.assert_blocked(self.git("push", "origin", "main", check=False))

    def test_secret_in_tag_annotation_blocks(self):
        self.git("tag", "-a", "message-tag", "-m", "access_token = " + self.token)
        self.assert_blocked(self.git("push", "origin", "refs/tags/message-tag", check=False))

    def test_non_commit_tag_blocks_without_skipping_objects(self):
        blob = self.git("rev-parse", "HEAD:.gitleaks.toml").stdout.strip()
        self.git("tag", "blob-tag", blob)
        self.assert_blocked(self.git("push", "origin", "refs/tags/blob-tag", check=False))

    def test_ref_deletion_succeeds(self):
        self.git("push", "origin", "HEAD:refs/heads/delete-me")
        self.assertEqual(self.git("push", "origin", ":refs/heads/delete-me").returncode, 0)


class PushSecretFailureTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "scripts/check-push-secrets"))
        self.globals = self.module["main"].__globals__

    def test_missing_scanner_blocks(self):
        with patch.dict(self.globals, scan_ranges=lambda _: ["a" * 40]), \
             patch("shutil.which", return_value=None), patch("pathlib.Path.is_file", return_value=False), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(self.module["main"](), 1)
        self.assertIn("Gitleaks is required", error.getvalue())

    def test_scanner_execution_failure_blocks(self):
        with patch.dict(self.globals, scan_ranges=lambda _: ["a" * 40]), \
             patch("shutil.which", return_value="gitleaks"), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 2)), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(self.module["main"](), 1)
        self.assertIn("could not complete", error.getvalue())

    def test_malformed_ref_input_blocks(self):
        with self.assertRaises(ValueError):
            self.module["scan_ranges"](["bad input"])

    def test_unknown_remote_base_scans_full_local_history(self):
        local, remote = "a" * 40, "b" * 40
        def git(*args):
            if args[-1].startswith(remote):
                raise subprocess.CalledProcessError(1, ["git"])
            return subprocess.CompletedProcess([], 0, local + "\n")
        with patch.dict(self.globals, git=git):
            self.assertEqual(self.module["scan_ranges"](
                [f"refs/heads/main {local} refs/heads/main {remote}"]), [local])


class RepositoryHookInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                                     GIT_CONFIG_NOSYSTEM="1"))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.module = runpy.run_path(str(ROOT / "bin/dot"))
        self.enterContext(patch.dict(self.module["configure_repository_hooks"].__globals__, ROOT=self.root))

    def test_install_is_idempotent_and_repository_local(self):
        configure = self.module["configure_repository_hooks"]
        self.assertEqual(configure(), 1)
        self.assertEqual(configure(), 0)
        path = subprocess.check_output(["git", "-C", str(self.root), "config", "--local",
                                        "--get", "core.hooksPath"], text=True).strip()
        self.assertEqual(path, str(self.root / ".githooks"))

    def test_custom_hooks_path_is_preserved(self):
        subprocess.run(["git", "-C", str(self.root), "config", "core.hooksPath", "custom-hooks"], check=True)
        with self.assertRaisesRegex(self.module["DotError"], "custom core.hooksPath"):
            self.module["configure_repository_hooks"]()

    def test_existing_pre_push_hook_is_preserved(self):
        hook = self.root / ".git/hooks/pre-push"
        hook.write_text("existing hook")
        with self.assertRaisesRegex(self.module["DotError"], "already has a pre-push hook"):
            self.module["configure_repository_hooks"]()
        self.assertEqual(hook.read_text(), "existing hook")


if __name__ == "__main__":
    unittest.main()
