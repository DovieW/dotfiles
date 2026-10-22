import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'davinci_resolve', Path(__file__).resolve().parents[1] / 'scripts/davinci-resolve.py')
resolve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolve)


class ResolveInstallTests(unittest.TestCase):
    def test_check_does_not_download_or_launch(self):
        with patch.object(sys, 'argv', ['installer', '--check']), \
                patch.object(resolve.Path, 'is_file', return_value=False), \
                patch.object(resolve.subprocess, 'run') as run, \
                patch.object(resolve, 'download_registered') as download:
            self.assertEqual(resolve.main(), 1)
            run.assert_not_called()
            download.assert_not_called()

    def test_incomplete_registration_stays_local(self):
        with patch.object(sys, 'stdin', io.StringIO('{}')), \
                patch.object(resolve.urllib.request, 'urlopen') as request:
            with self.assertRaisesRegex(ValueError, 'street'):
                resolve.download_registered()
            request.assert_not_called()

    def test_t64_bypass_requires_installed_packages_and_loadable_libraries(self):
        from subprocess import CompletedProcess
        installed = CompletedProcess([], 0, 'install ok installed', '')
        with patch.object(resolve.subprocess, 'run', return_value=installed), \
                patch.object(resolve.ctypes, 'CDLL') as load:
            self.assertTrue(resolve.ubuntu_t64_dependencies_ready())
            self.assertEqual(load.call_count, 4)
        with patch.object(resolve.subprocess, 'run', return_value=installed), \
                patch.object(resolve.ctypes, 'CDLL', side_effect=OSError('missing')):
            self.assertFalse(resolve.ubuntu_t64_dependencies_ready())
        missing = CompletedProcess([], 1, '', '')
        with patch.object(resolve.subprocess, 'run', return_value=missing), \
                patch.object(resolve.ctypes, 'CDLL') as load:
            self.assertFalse(resolve.ubuntu_t64_dependencies_ready())
            load.assert_not_called()

    def test_running_or_unavailable_process_inspection_blocks_replacement(self):
        from subprocess import CompletedProcess
        for code in (0, 2):
            with self.subTest(code=code), \
                    patch.object(sys, 'argv', ['installer', '--archive', '/missing.zip']), \
                    patch.object(resolve.subprocess, 'run', return_value=CompletedProcess([], code)) as run:
                with self.assertRaises(SystemExit):
                    resolve.main()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0], ['pgrep', '-f', r'^/opt/resolve/bin/resolve([[:space:]]|$)'])

    def test_vendor_form_product_and_download_host(self):
        registration = {k: 'test' for k in (
            'firstname', 'lastname', 'email', 'phone', 'country', 'street', 'city', 'state')}
        release = {'numericDate': 1, 'urls': {'Linux': [{
            'product': 'davinci-resolve', 'downloadId': 'test', 'beta': 255}]}}
        responses = [io.BytesIO(json.dumps({'downloads': [release]}).encode()),
                     io.BytesIO(json.dumps('https://untrusted.example/installer.zip').encode())]
        with patch.object(sys, 'stdin', io.StringIO(json.dumps(registration))), \
                patch.object(resolve.urllib.request, 'urlopen', side_effect=responses) as request:
            with self.assertRaisesRegex(ValueError, 'unexpected download host'):
                resolve.download_registered()
            body = json.loads(request.call_args_list[1].args[0].data)
            self.assertEqual(body['product'], 'DaVinci Resolve')
            self.assertEqual(body['platform'], 'Linux')
            self.assertEqual(request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
