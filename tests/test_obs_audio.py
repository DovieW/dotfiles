import json
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
configure = runpy.run_path(str(ROOT / 'scripts/obs-audio-profile'))['configure']
PRESET = json.loads((ROOT / 'config/obs/audio-preset.json').read_text())


class AudioProfileTests(unittest.TestCase):
    def scene(self):
        return {'DesktopAudioDevice1': {'settings': {'device_id': 'default'}},
                'AuxAudioDevice1': {'settings': {'device_id': 'default'}},
                'sources': [{'name': 'mic', 'id': 'pulse_input_capture', 'settings': {'device_id': 'usb'}},
                            {'name': 'desktop', 'id': 'pulse_output_capture', 'settings': {'device_id': 'headphones'}}]}

    def test_duplicate_removal_tracks_and_idempotence(self):
        before = self.scene()
        result = configure(before, PRESET)
        self.assertIn('AuxAudioDevice1', before)
        self.assertNotIn('AuxAudioDevice1', result)
        self.assertNotIn('DesktopAudioDevice1', result)
        self.assertEqual([s['mixers'] for s in result['sources']], [3, 5])
        self.assertEqual(configure(result, PRESET), result)
        for source in result['sources']:
            self.assertEqual(source['filters'][-1]['id'], 'limiter_filter')
            self.assertEqual(source['monitoring_type'], 0)

    def test_custom_filters_are_not_overwritten(self):
        scene = self.scene()
        scene['sources'][0]['filters'] = [{'name': 'My EQ'}]
        with self.assertRaises(ValueError):
            configure(scene, PRESET)

    def test_extra_global_device_requires_review(self):
        scene = self.scene()
        scene['AuxAudioDevice2'] = {'settings': {'device_id': 'another-mic'}}
        with self.assertRaises(ValueError):
            configure(scene, PRESET)

    def test_ambiguous_scene_requires_review(self):
        scene = self.scene()
        scene['sources'].append(scene['sources'][0].copy())
        with self.assertRaises(ValueError):
            configure(scene, PRESET)


if __name__ == '__main__':
    unittest.main()
