#!/usr/bin/env python3
"""Run Blackmagic's registered Linux installer without storing registration data."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import shutil
import sys
import zipfile


def configure_display(check=False):
    """Choose a supported native scale without replacing other preferences."""
    try:
        result = subprocess.run(['kscreen-doctor', '-j'], capture_output=True,
                                text=True, timeout=5, check=True)
        outputs = [o for o in json.loads(result.stdout)['outputs']
                   if o.get('enabled') and o.get('connected')]
        primary = min(outputs, key=lambda o: o.get('priority') or 999)
        scale = float(primary['scale']) * 100
        if not 50 <= scale <= 400:
            raise ValueError('invalid display scale')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        print('Resolve display scale pending: KDE display information is unavailable.')
        return 0
    # Fractional values such as 175 are not effective in this Resolve build.
    # Prefer the smaller native step when equally close (175 -> 150).
    desired = min((100, 150, 200), key=lambda value: (abs(value - scale), value))
    config = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'DaVinciResolve/configs/config.user.xml'
    if not config.is_file():
        print('Resolve display scale pending: launch Resolve once, close it, then reapply.')
        return 0
    source = config.read_text()
    pattern = r'<DisplayScale>[^<]*</DisplayScale>'
    matches = re.findall(pattern, source)
    if len(matches) != 1:
        raise ValueError('Resolve display-scale preference is missing or ambiguous; leaving preferences untouched.')
    replacement = f'<DisplayScale>{desired}</DisplayScale>'
    if matches[0] == replacement:
        print(f'Resolve native display scale is {desired}%.')
        return 0
    if check:
        print(f'Resolve native display scale requires {desired}%.')
        return 1
    active = subprocess.run(['pgrep', '-f', r'^/opt/resolve/bin/resolve([[:space:]]|$)'], capture_output=True)
    if active.returncode != 1:
        print(f'Resolve display scale pending: save and close Resolve before applying {desired}%.')
        return 0
    backup = config.with_name('config.user.xml.before-dotfiles-scaling')
    if not backup.exists():
        shutil.copy2(config, backup)
    with tempfile.NamedTemporaryFile(mode='w', dir=config.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(re.sub(pattern, replacement, source))
            output.close()
            temporary.chmod(config.stat().st_mode & 0o777)
            temporary.replace(config)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'Configured Resolve native display scale to {desired}%.')
    return 0


def ubuntu_t64_dependencies_ready():
    libraries = {
        'libapr1t64': 'libapr-1.so.0',
        'libaprutil1t64': 'libaprutil-1.so.0',
        'libasound2t64': 'libasound.so.2',
        'libglib2.0-0t64': 'libglib-2.0.so.0',
    }
    for package, library in libraries.items():
        result = subprocess.run(
            ['dpkg-query', '-W', '-f=${Status}', package], capture_output=True, text=True)
        if result.returncode != 0 or result.stdout.strip() != 'install ok installed':
            return False
        try:
            ctypes.CDLL(library)
        except OSError:
            return False
    return True


def download_registered():
    """Read registration from stdin; keep it out of argv, logs and disk."""
    registration = json.load(sys.stdin)
    required = ('firstname', 'lastname', 'email', 'phone', 'country', 'street', 'city', 'state')
    missing = [field for field in required if not registration.get(field)]
    if missing:
        raise ValueError('Missing Blackmagic registration fields: ' + ', '.join(missing))
    with urllib.request.urlopen('https://www.blackmagicdesign.com/api/support/us/downloads.json', timeout=60) as response:
        releases = json.load(response)['downloads']
    candidates = [r for r in releases if 'Linux' in r.get('urls', {})
                  and r['urls']['Linux'][0].get('product') == 'davinci-resolve'
                  and r['urls']['Linux'][0].get('beta', 255) == 255]
    release = max(candidates, key=lambda r: r['numericDate'])
    item = release['urls']['Linux'][0]
    registration.update(origin='www.blackmagicdesign.com', platform='Linux', product='DaVinci Resolve')
    request = urllib.request.Request(
        'https://www.blackmagicdesign.com/api/register/us/download/' + item['downloadId'],
        data=json.dumps(registration).encode(), headers={'Content-Type': 'application/json',
            'Origin': 'https://www.blackmagicdesign.com',
            'Referer': 'https://www.blackmagicdesign.com/support/'})
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
    parser.add_argument('--configure-display', action='store_true', help='Match native UI scale to the primary KDE display while Resolve is closed.')
    parser.add_argument('--download', action='store_true', help='Read vendor registration JSON from stdin, then download and install.')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('DaVinci Resolve requires native x86_64 Linux here.')
    if args.download and (args.check or args.archive):
        parser.error('--download cannot be combined with --check or --archive.')
    if args.configure_display:
        if args.download or args.archive:
            parser.error('--configure-display cannot be combined with download or archive installation.')
        return configure_display(check=args.check)
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
    # Qt renames the process to 'GUI Thread' after startup; match the
    # vendor launch command rather than the mutable process name.
    result = subprocess.run(
        ['pgrep', '-f', r'^/opt/resolve/bin/resolve([[:space:]]|$)'],
        capture_output=True, text=True)
    if result.returncode != 1:
        parser.error('Close Resolve after saving work, or resolve the process-inspection failure, before installing.')
    archive = archive.expanduser().resolve(strict=True)
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'dotfiles'
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='resolve-', dir=cache) as work:
        with zipfile.ZipFile(archive) as bundle:
            candidates = [i for i in bundle.infolist()
                          if i.filename.startswith('DaVinci_Resolve_')
                          and i.filename.endswith('_Linux.run')
                          and '/' not in i.filename]
            if len(candidates) != 1:
                parser.error('Expected one official free-edition Linux .run installer at ZIP root.')
            installer = Path(bundle.extract(candidates[0], work))
        installer.chmod(0o700)
        # The vendor checks old Debian package names, rejecting Ubuntu's t64
        # replacements. Bypass only when every replacement is installed AND its
        # actual shared library loads. This does not disable GPU/runtime checks.
        compatibility = ubuntu_t64_dependencies_ready()
        assignments = ['QT_QPA_PLATFORM=offscreen']
        if compatibility:
            assignments.append('SKIP_PACKAGE_CHECK=1')
        command = ['/usr/bin/env', *assignments, str(installer), '-i', '-y', '-a']
        if os.geteuid() != 0:
            if subprocess.run(['sudo', '-n', 'true'], capture_output=True).returncode == 0:
                command = ['sudo', '-n', *command]
            else:
                command = ['pkexec', *command]
        subprocess.run(command, check=True)
    if not binary.is_file():
        print('Installer exited without creating /opt/resolve/bin/resolve.')
        return 1
    print('DaVinci Resolve installed. Launch from the application menu to verify GPU operation.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as error:
        print(f'Blackmagic download request failed (HTTP {error.code}). '
              'Check registration fields or use the official website to download the archive.', file=sys.stderr)
        raise SystemExit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
