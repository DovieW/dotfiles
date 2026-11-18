import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "config/power/dot-audio-mute"


class AudioMuteTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCRIPT))
        self.timeout = self.module["DisplayTimeout"]()

    def test_mutes_once_after_continuous_display_off_time(self):
        mute = Mock(return_value=True)
        with patch.dict(self.timeout.update.__globals__, {"mute_output": mute}):
            self.timeout.update(True, 10)
            self.timeout.update(True, 1809)
            mute.assert_not_called()
            self.timeout.update(True, 1810)
            self.timeout.update(True, 1820)
        mute.assert_called_once_with("displays off for 30 minutes")

    def test_display_on_resets_the_countdown(self):
        with patch.dict(self.timeout.update.__globals__, {"mute_output": lambda _: True}):
            self.timeout.update(True, 0)
            self.timeout.update(False, 1790)
            self.timeout.update(True, 1800)
            self.timeout.update(True, 1810)
            self.assertFalse(self.timeout.muted)
            self.timeout.update(True, 3600)
            self.assertTrue(self.timeout.muted)

    def test_retries_when_the_audio_output_is_unavailable(self):
        with patch.dict(self.timeout.update.__globals__, {"mute_output": lambda _: False}):
            self.timeout.update(True, 0)
            self.timeout.update(True, 1800)
            self.assertFalse(self.timeout.muted)
        with patch.dict(self.timeout.update.__globals__, {"mute_output": lambda _: True}):
            self.timeout.update(True, 1810)
            self.assertTrue(self.timeout.muted)

    def test_requires_all_displays_to_report_off(self):
        read_displays = self.module["displays_off"]
        with patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                [], 0, stdout="dpms mode for screen eDP-1: off\ndpms mode for screen DP-1: on\n",
            )
            self.assertFalse(read_displays())
            run.return_value.stdout = run.return_value.stdout.replace(": on", ": off")
            self.assertTrue(read_displays())
            run.return_value.stdout = ""
            with self.assertRaises(ValueError):
                read_displays()


if __name__ == "__main__":
    unittest.main()
