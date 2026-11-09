#!/usr/bin/python3 -I
"""Root-owned helper: list boot candidates or select one for the next boot."""
import json
import re
import subprocess
import sys

BLESS = '/usr/bin/asahi-bless'
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
    return parse_volumes(result.stdout)

def main(args):
    if args == ['--list']:
        print(json.dumps(list_volumes()))
    elif len(args) == 2 and args[0] == '--select-next' and re.fullmatch(r'[0-9]+', args[1]):
        index = int(args[1])
        if index not in [v['index'] for v in list_volumes()]:
            raise ValueError('Selected boot volume is no longer available.')
        subprocess.run([BLESS, '--next', '--set-boot', str(index), '--yes'], env=ENV, check=True)
    else:
        raise ValueError('Expected --list or --select-next INDEX.')

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f'Boot selection failed: {error}', file=sys.stderr)
        sys.exit(1)
