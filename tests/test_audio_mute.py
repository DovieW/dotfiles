import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "config/power/dot-audio-mute"


class AudioMuteTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCRIPT))
        self.schedule = Mock(return_value=42)
        self.cancel = Mock()
        self.timeout = self.module["DisplayTimeout"](self.schedule, self.cancel)

    def test_arms_one_shot_timer_when_displays_turn_off(self):
        zero_volume = Mock()
        with patch.dict(self.timeout.elapsed.__globals__, {"zero_volume": zero_volume}):
            self.timeout.update(False, False)
            self.schedule.assert_not_called()
            self.timeout.update(True, False)
            self.schedule.assert_called_once_with(1800, self.timeout.elapsed)
            zero_volume.assert_not_called()
            self.assertFalse(self.timeout.elapsed())
            self.timeout.update(True, False)
            self.schedule.assert_called_once()
        zero_volume.assert_called_once_with("displays off for 30 minutes")

    def test_display_on_cancels_the_countdown(self):
        self.timeout.update(True, False)
        self.timeout.update(False, False)
        self.cancel.assert_called_once_with(42)
        self.timeout.update(True, False)
        self.assertEqual(self.schedule.call_count, 2)

    def test_sleep_cancels_timer_and_wake_rearms_if_displays_stay_off(self):
        self.timeout.update(True, False)
        self.timeout.update(True, True)
        self.cancel.assert_called_once_with(42)
        self.schedule.assert_called_once()
        self.timeout.update(True, False)
        self.assertEqual(self.schedule.call_count, 2)

    def test_changes_volume_level_and_handles_missing_audio(self):
        zero_volume = self.module["zero_volume"]
        with patch("subprocess.run") as run:
            self.assertTrue(zero_volume("test"))
            self.assertEqual(
                run.call_args.args[0], ["/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0"],
            )
            run.side_effect = subprocess.CalledProcessError(1, "wpctl")
            with self.assertLogs(level="WARNING"):
                self.assertFalse(zero_volume("test"))


if __name__ == "__main__":
    unittest.main()
