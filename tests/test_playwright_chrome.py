"""Verify the guards around Playwright's personal Chrome attachment."""
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("playwright_chrome", str(ROOT / "scripts/playwright-chrome"))
spec = importlib.util.spec_from_loader(loader.name, loader)
chrome = importlib.util.module_from_spec(spec)
loader.exec_module(chrome)


class ChromeAttachmentTest(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(chrome, "RUNTIME", Path(temp)))
        self.list = self.enterContext(patch.object(chrome, "capture", return_value='{"browsers": []}'))
        self.browser = self.enterContext(patch.object(chrome, "check_browser", return_value=123))
        self.running = self.enterContext(patch.object(chrome, "running_browser", return_value=123))
        self.token = self.enterContext(patch.object(chrome, "read_token", return_value="sample-extension-token"))
        self.launch = self.enterContext(patch.object(chrome.subprocess, "run"))

    def test_existing_session_is_never_replaced(self):
        self.list.return_value = '{"browsers": [{"name": "mine"}]}'
        with self.assertRaisesRegex(chrome.Error, "already open"):
            chrome.attach("Default", "mine", {})
        self.browser.assert_not_called()
        self.launch.assert_not_called()

    def test_attach_declines_when_browser_changes_or_token_is_unavailable(self):
        self.running.return_value = 456
        with self.assertRaisesRegex(chrome.Error, "Chrome changed"):
            chrome.attach("Default", "mine", {})
        self.running.return_value = 123
        self.token.side_effect = chrome.Error("Enroll the token")
        with self.assertRaisesRegex(chrome.Error, "Enroll the token"):
            chrome.attach("Default", "mine", {})
        self.launch.assert_not_called()

    def test_only_guarded_attach_receives_the_profile_token(self):
        self.launch.return_value = subprocess.CompletedProcess([], 0, self.token.return_value, "")
        env = {"PLAYWRIGHT_MCP_CDP_ENDPOINT": "elsewhere", "DEBUG": "*", "DISPLAY": ":0"}
        out = io.StringIO()
        with redirect_stdout(out):
            chrome.attach("Default", "mine", env)
        self.assertNotIn(chrome.TOKEN_ENV, self.list.call_args.kwargs["env"])
        command = self.launch.call_args.args[0]
        forwarded = self.launch.call_args.kwargs["env"]
        self.assertIn("--extension=chrome", command)
        self.assertIn("--no-tab-group", command)
        self.assertIn("--session=mine", command)
        self.assertNotIn(self.token.return_value, " ".join(command))
        self.assertEqual(forwarded[chrome.TOKEN_ENV], self.token.return_value)
        self.assertEqual(forwarded["PLAYWRIGHT_MCP_PROFILE_DIR_NAME"], "Default")
        self.assertEqual(forwarded["DISPLAY"], ":0")
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", forwarded)
        self.assertNotIn("DEBUG", forwarded)
        self.assertEqual(out.getvalue(), "[redacted]")
