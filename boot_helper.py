#!/usr/bin/python3 -I
"""Root-owned helper: list boot candidates or select one for the next boot."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

BLESS = '/usr/bin/asahi-bless'
# Isolated Python does not import from a user-controlled checkout.
TRUSTED = '/usr/local/lib/omarchy-reboot-macos'
sys.path.insert(0, TRUSTED)
try:
    from apfs_metadata import system_metadata
except ImportError:
    def system_metadata(): return []

ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}

def parse_volumes(output):
    volumes = []
    for line in output.splitlines():
        match = re.fullmatch(r'\s*(\*)?\s*(\d+)\) (.+)', line)
        if match:
            volumes.append({'index': int(match[2]), 'name': match[3], 'current': bool(match[1])})
    if not volumes or len({v['index'] for v in volumes}) != len(volumes):
        raise ValueError('Could not read an unambiguous boot-volume list.')
    return volumes

def list_volumes():
    result = subprocess.run([BLESS, '--list-volumes'], env=ENV, check=True,
                            text=True, capture_output=True)
    volumes = parse_volumes(result.stdout)
    metadata = system_metadata()
    for volume in volumes:
        matches = [m for m in metadata if m['name'] == volume['name']]
        unique = len([v for v in volumes if v['name'].casefold() == volume['name'].casefold()]) == 1
        volume['os'] = 'unknown'
        identity = 'name:' + volume['name']
        if len(matches) == 1 and unique:
            record = matches[0]
            identity = record['partition'] + ':' + record['vg_uuid']
            if record['sealed_system']:
                volume['os'] = 'macos'
        volume['id'] = hashlib.sha256(identity.encode()).hexdigest()
        volume['selectable'] = unique
    return volumes

def main(args):
    if args == ['--list']:
        print(json.dumps(list_volumes()))
    elif len(args) == 2 and args[0] == '--select-next' and re.fullmatch(r'[a-f0-9]{64}', args[1]):
        matches = [v for v in list_volumes() if v['id'] == args[1] and v['selectable']]
        if len(matches) != 1:
            raise ValueError('Selected boot volume is unavailable or ambiguous.')
        # Use the exact unique name, not the list index: asahi-bless can enumerate
        # volume groups in a different order on its next invocation.
        subprocess.run([BLESS, '--next', '--set-boot', matches[0]['name'], '--yes'], env=ENV, check=True)
    elif len(args) == 2 and args[0] == '--clear-next' and re.fullmatch(r'[a-f0-9]{64}', args[1]):
        matches = [v for v in list_volumes() if v['id'] == args[1] and v['selectable']]
        target = subprocess.run([BLESS, '--next', '--get-boot'], env=ENV, check=True, text=True, capture_output=True).stdout.strip()
        if len(matches) != 1 or target != matches[0]['name']:
            raise ValueError('Next boot target changed; refusing to clear another selection.')
        subprocess.run([BLESS, '--clear-next'], env=ENV, check=True)
    else:
        raise ValueError('Expected --list, --select-next ID, or --clear-next.')

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Boot selection failed: {error}', file=sys.stderr)
        sys.exit(1)
