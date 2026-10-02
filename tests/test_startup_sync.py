import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class StartupSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.remote = base / "remote.git"
        self.writer = base / "writer"
        self.checkout = base / "checkout"
        self.environment = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        for name in ("DOTFILES_TESTING", "DOTFILES_STARTUP_CHECKED"):
            self.environment.pop(name, None)
        self.git(base, "init", "--bare", "--initial-branch=master", str(self.remote))
        self.git(base, "init", "--initial-branch=master", str(self.writer))
        (self.writer / "settings.txt").write_text("original\n")
        (self.writer / "notes.txt").write_text("notes\n")
        (self.writer / "bin").mkdir()
        (self.writer / "bin/dot").write_bytes((ROOT / "bin/dot").read_bytes())
        self.commit(self.writer)
        self.git(self.writer, "remote", "add", "origin", str(self.remote))
        self.git(self.writer, "push", "-u", "origin", "master")
        self.git(base, "clone", str(self.remote), str(self.checkout))
        self.module = runpy.run_path(str(ROOT / "bin/dot"))
        self.update = self.module["update_dotfiles_before_run"]
        patch = mock.patch.dict(self.update.__globals__, {"ROOT": self.checkout})
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, self.environment, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def git(self, directory, *arguments):
        return subprocess.run(
            ["git", *arguments], cwd=directory, env=self.environment,
            text=True, capture_output=True, check=True,
        ).stdout.strip()

    def commit(self, directory):
        self.git(directory, "add", ".")
        self.git(directory, "-c", "commit.gpgsign=false", "commit", "-m", "fixture")

    def publish(self, filename="settings.txt", content="remote update\n"):
        (self.writer / filename).write_text(content)
        self.commit(self.writer)
        self.git(self.writer, "push")

    def check_update(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            updated = self.update()
        return updated, output.getvalue()

    def test_current_checkout_is_quiet(self):
        self.assertEqual(self.check_update(), (False, ""))

    def test_fast_forward_uses_configured_remote(self):
        self.git(self.checkout, "remote", "rename", "origin", "upstream")
        self.publish()
        updated, output = self.check_update()
        self.assertTrue(updated)
        self.assertIn("1 upstream commit(s) missing", output)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.git(self.writer, "rev-parse", "HEAD"))
        self.assertEqual((self.checkout / "settings.txt").read_text(), "remote update\n")

    def test_ahead_only_branch_is_preserved(self):
        (self.checkout / "settings.txt").write_text("local commit\n")
        self.commit(self.checkout)
        previous = self.git(self.checkout, "rev-parse", "HEAD")
        self.assertEqual(self.check_update(), (False, ""))
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), previous)

    def test_unrelated_local_edits_survive_pull(self):
        (self.checkout / "notes.txt").write_text("keep local edits\n")
        self.publish()
        self.assertTrue(self.check_update()[0])
        self.assertEqual((self.checkout / "notes.txt").read_text(), "keep local edits\n")
        self.assertEqual(self.git(self.checkout, "stash", "list"), "")

    def test_overlapping_local_edits_warn_without_stashing(self):
        self.git(self.checkout, "config", "pull.rebase", "true")
        self.git(self.checkout, "config", "rebase.autoStash", "true")
        self.git(self.checkout, "config", "merge.autoStash", "true")
        (self.checkout / "settings.txt").write_text("keep local settings\n")
        previous = self.git(self.checkout, "rev-parse", "HEAD")
        self.publish()
        updated, output = self.check_update()
        self.assertFalse(updated)
        self.assertIn("Could not pull 1 missing commit(s)", output)
        self.assertIn("Continuing with the local dotfiles checkout", output)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), previous)
        self.assertEqual((self.checkout / "settings.txt").read_text(), "keep local settings\n")
        self.assertEqual(self.git(self.checkout, "stash", "list"), "")

    def test_divergence_warns_without_merging(self):
        self.git(self.checkout, "config", "pull.ff", "false")
        self.git(self.checkout, "config", "pull.rebase", "true")
        (self.checkout / "notes.txt").write_text("local commit\n")
        self.commit(self.checkout)
        previous = self.git(self.checkout, "rev-parse", "HEAD")
        self.publish()
        updated, output = self.check_update()
        self.assertFalse(updated)
        self.assertIn("branches have diverged", output)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), previous)
        self.assertFalse((self.checkout / ".git/MERGE_HEAD").exists())
        self.assertFalse((self.checkout / ".git/rebase-merge").exists())

    def test_unavailable_remote_warns(self):
        self.git(self.checkout, "remote", "set-url", "origin", str(self.remote.parent / "missing.git"))
        updated, output = self.check_update()
        self.assertFalse(updated)
        self.assertIn("Fetching 'origin' failed", output)

    def test_missing_upstream_warns(self):
        self.git(self.checkout, "branch", "--unset-upstream")
        updated, output = self.check_update()
        self.assertFalse(updated)
        self.assertIn("no configured upstream", output)

    def test_detached_head_warns(self):
        self.git(self.checkout, "checkout", "--detach")
        updated, output = self.check_update()
        self.assertFalse(updated)
        self.assertIn("Detached HEAD", output)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group timeout")
    def test_timeout_terminates_git_and_its_child(self):
        command = self.module["startup_git"]
        started = time.monotonic()
        with mock.patch.dict(command.__globals__, {"STARTUP_GIT_TIMEOUT": 0.1}):
            result = command(["-c", "alias.hang=!sleep 30", "hang"], self.environment)
        self.assertEqual(result.returncode, 124)
        self.assertLess(time.monotonic() - started, 3)

    def test_successful_pull_executes_new_cli_with_same_arguments(self):
        self.publish("bin/dot", "import json, os, sys\nprint(json.dumps([sys.argv[1:], os.environ.get('DOTFILES_STARTUP_CHECKED')]))\n")
        result = subprocess.run(
            [sys.executable, str(self.checkout / "bin/dot"), "new-command", "--some-option", "two words"],
            env=self.environment, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [["new-command", "--some-option", "two words"], str(self.checkout)])
        self.assertIn("restarting with the updated CLI", result.stderr)

    def test_warning_still_runs_requested_command(self):
        self.git(self.checkout, "remote", "set-url", "origin", str(self.remote.parent / "missing.git"))
        action = mock.Mock()
        parser = mock.Mock()
        parser.parse_args.return_value = argparse.Namespace(func=action)
        main = self.module["main"]
        output = io.StringIO()
        with (
            mock.patch.dict(main.__globals__, {"build_parser": lambda: parser}),
            mock.patch("sys.argv", ["dot", "some-command"]),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(main(), 0)
        action.assert_called_once()
        self.assertIn("Fetching 'origin' failed", output.getvalue())

    def test_nested_invocations_and_help_do_not_fetch(self):
        main = self.module["main"]
        action = mock.Mock()
        parser = mock.Mock()
        parser.parse_args.return_value = argparse.Namespace(func=action)
        update = mock.Mock(return_value=False)
        with mock.patch.dict(main.__globals__, {"build_parser": lambda: parser, "update_dotfiles_before_run": update}):
            with mock.patch("sys.argv", ["dot", "some-command"]):
                self.assertEqual(main(), 0)
                self.assertEqual(main(), 0)
            self.assertEqual(update.call_count, 1)
            os.environ.pop("DOTFILES_STARTUP_CHECKED")
            with mock.patch("sys.argv", ["dot", "--help"]):
                self.assertEqual(main(), 0)
            self.assertEqual(update.call_count, 1)


if __name__ == "__main__":
    unittest.main()
