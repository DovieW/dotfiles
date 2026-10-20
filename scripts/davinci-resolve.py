#!/usr/bin/env python3
"""Run Blackmagic's registered Linux installer without storing registration data."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import urllib.parse
import urllib.request
import shutil
import sys
import zipfile


def download_registered():
    """Read registration from stdin; keep it out of argv, logs and disk."""
    registration = json.load(sys.stdin)
    with urllib.request.urlopen('https://www.blackmagicdesign.com/api/support/us/downloads.json', timeout=60) as response:
        releases = json.load(response)['downloads']
    candidates = [r for r in releases if 'Linux' in r.get('urls', {})
                  and r['urls']['Linux'][0].get('product') == 'davinci-resolve'
                  and r['urls']['Linux'][0].get('beta', 255) == 255]
    release = max(candidates, key=lambda r: r['numericDate'])
    item = release['urls']['Linux'][0]
    registration.update(origin='www.blackmagicdesign.com', platform='linux', product='davinci-resolve')
    request = urllib.request.Request(
        'https://www.blackmagicdesign.com/api/register/us/download/' + item['downloadId'],
        data=json.dumps(registration).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        url = json.load(response)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'sw.blackmagicdesign.com':
        raise ValueError('Vendor returned an unexpected download host.')
    destination = Path.home() / 'Downloads'
    destination.mkdir(exist_ok=True)
    target = destination / f"DaVinci_Resolve_{item['major']}.{item['minor']}.{item['releaseNum']}_Linux.zip"
    with tempfile.NamedTemporaryFile(dir=destination, prefix='.resolve-', delete=False) as output:
        temporary = Path(output.name)
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                if urllib.parse.urlsplit(response.url).hostname != 'sw.blackmagicdesign.com':
                    raise ValueError('Unexpected download redirect host.')
                shutil.copyfileobj(response, output)
            output.close()
            with zipfile.ZipFile(temporary) as bundle:
                if bundle.testzip() is not None:
                    raise ValueError('Installer ZIP failed its CRC check.')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"Downloaded {item['downloadTitle']} from Blackmagic Design.")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--ensure', action='store_true')
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--download', action='store_true', help='Read vendor registration JSON from stdin, then download and install.')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('DaVinci Resolve requires native x86_64 Linux here.')
    if args.download and (args.check or args.archive):
        parser.error('--download cannot be combined with --check or --archive.')
    binary = Path('/opt/resolve/bin/resolve')
    if args.check:
        if not binary.is_file() or not os.access(binary, os.X_OK):
            print('DaVinci Resolve is not installed.')
            return 1
        print('DaVinci Resolve executable is available; GPU and GUI operation require a launch check.')
        return 0
    if binary.exists() and args.archive is None and not args.download:
        print('DaVinci Resolve is installed. Updates require an explicit --archive after saving work.')
        return 0
    archive = download_registered() if args.download else args.archive
    if archive is None:
        archives = sorted((Path.home() / 'Downloads').glob('DaVinci_Resolve_*_Linux.zip'))
        if len(archives) == 1:
            archive = archives[0]
        else:
            print('DaVinci Resolve pending: supply one official free Linux ZIP in ~/Downloads '
                  'or use scripts/install-davinci-resolve --archive PATH. See docs/davinci-resolve.md.')
            return 0
    # Never replace a running editor or its loaded libraries, including other users.
    result = subprocess.run(['pgrep', '-x', 'resolve'], capture_output=True, text=True)
    if result.returncode != 1:
        parser.error('Close Resolve after saving work, or resolve the process-inspection failure, before installing.')
    archive = archive.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='dotfiles-resolve-') as work:
        with zipfile.ZipFile(archive) as bundle:
            candidates = [i for i in bundle.infolist()
                          if i.filename.startswith('DaVinci_Resolve_')
                          and i.filename.endswith('_Linux.run')
                          and '/' not in i.filename]
            if len(candidates) != 1:
                parser.error('Expected one official free-edition Linux .run installer at ZIP root.')
            installer = Path(bundle.extract(candidates[0], work))
        installer.chmod(0o700)
        # Keep the vendor's interactive license and authorization flow. No invented
        # registration details, silent license acceptance, or package-check bypass.
        environment = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN='1')
        subprocess.run([str(installer)], env=environment, check=True)
    if not binary.is_file():
        print('Installer exited without creating /opt/resolve/bin/resolve.')
        return 1
    print('DaVinci Resolve installed. Launch from the application menu to verify GPU operation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
