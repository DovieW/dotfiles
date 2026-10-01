#!/usr/bin/env python3
import errno
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "config/git/bin/git-switcher"


class GitSwitcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("commit", "-q", "--allow-empty", "-m", "initial")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("branch", "feature/nested")
        self.git("push", "-q", "-u", "origin", "feature/nested")

    def git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=check, capture_output=True, text=True)

    def exists(self, ref, remote=False):
        location = self.remote if remote else self.repo
        return subprocess.run(["git", "-C", str(location), "show-ref", "--verify", "--quiet", ref]).returncode == 0

    def delete(self, branch, prompts):
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.repo)
            os.execv(str(SCRIPT), [str(SCRIPT), "--delete", branch])
        output = b""
        consumed = 0
        deadline = time.monotonic() + 10
        try:
            for prompt, answer in prompts:
                needle = prompt.encode()
                while needle not in output[consumed:]:
                    if time.monotonic() > deadline:
                        self.fail(f"Timed out waiting for {prompt!r}: {output!r}")
                    if select.select([fd], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(fd, 65536)
                        except OSError as error:
                            if error.errno == errno.EIO:
                                chunk = b""
                            else:
                                raise
                        if not chunk:
                            self.fail(f"Helper exited before {prompt!r}: {output!r}")
                        output += chunk
                consumed = len(output)
                os.write(fd, (answer + "\n").encode())
            while time.monotonic() < deadline:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    pid = None
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                    return output.decode()
                if select.select([fd], [], [], 0.1)[0]:
                    try:
                        output += os.read(fd, 65536)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
            self.fail(f"Helper did not exit: {output!r}")
        finally:
            os.close(fd)
            if pid is not None:
                os.kill(pid, 9)
                os.waitpid(pid, 0)

    def test_declining_default_preserves_local_and_remote(self):
        self.delete("feature/nested", [("[y/N]", ""), ("Press Enter", "")])
        self.assertTrue(self.exists("refs/heads/feature/nested"))
        self.assertTrue(self.exists("refs/heads/feature/nested", remote=True))

    def test_remote_deletion_requires_separate_confirmation(self):
        self.delete("feature/nested", [("[y/N]", "y"), ("Also delete", "n"), ("Press Enter", "")])
        self.assertFalse(self.exists("refs/heads/feature/nested"))
        self.assertTrue(self.exists("refs/heads/feature/nested", remote=True))

    def test_confirmed_deletion_uses_upstream_name(self):
        self.git("branch", "-m", "feature/nested", "renamed")
        self.delete("renamed", [("[y/N]", "yes"), ("Also delete 'feature/nested'", "y"), ("Press Enter", "")])
        self.assertFalse(self.exists("refs/heads/renamed"))
        self.assertFalse(self.exists("refs/heads/feature/nested", remote=True))
        self.assertFalse(self.exists("refs/remotes/origin/feature/nested"))

    def test_selecting_remote_branch_deletes_only_remote(self):
        self.delete("origin/feature/nested", [("[y/N]", "y"), ("Press Enter", "")])
        self.assertTrue(self.exists("refs/heads/feature/nested"))
        self.assertFalse(self.exists("refs/heads/feature/nested", remote=True))

    def test_current_branch_is_protected(self):
        output = self.delete("main", [("[y/N]", "y"), ("Press Enter", "")])
        self.assertIn("cannot delete branch", output.lower())
        self.assertTrue(self.exists("refs/heads/main"))

    def test_unmerged_branch_is_protected(self):
        self.git("switch", "-q", "-c", "unmerged")
        self.git("commit", "-q", "--allow-empty", "-m", "unmerged work")
        self.git("switch", "-q", "main")
        output = self.delete("unmerged", [("[y/N]", "y"), ("Press Enter", "")])
        self.assertIn("not fully merged", output)
        self.assertTrue(self.exists("refs/heads/unmerged"))

    def test_list_excludes_remote_head_and_preserves_nested_names(self):
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/feature/nested")
        result = subprocess.run([str(SCRIPT), "--list"], cwd=self.repo, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.splitlines(), ["feature/nested", "main"])
        result = subprocess.run([str(SCRIPT), "--list", "remote"], cwd=self.repo, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.splitlines(), ["origin/feature/nested"])

    def test_remote_selection_creates_local_tracking_branch(self):
        self.git("branch", "-d", "feature/nested")
        subprocess.run([str(SCRIPT), "--switch", "origin/feature/nested", "Remote › "], cwd=self.repo, check=True, capture_output=True)
        self.assertEqual(self.git("branch", "--show-current").stdout.strip(), "feature/nested")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "@{upstream}").stdout.strip(), "origin/feature/nested")

    def test_remote_selection_switches_existing_local_branch(self):
        subprocess.run([str(SCRIPT), "--switch", "origin/feature/nested", "Remote › "], cwd=self.repo, check=True, capture_output=True)
        self.assertEqual(self.git("branch", "--show-current").stdout.strip(), "feature/nested")


if __name__ == "__main__":
    unittest.main()
