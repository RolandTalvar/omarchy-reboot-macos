#!/usr/bin/python3
"""Detect macOS by label; ask the user when labels cannot identify it."""
import json
import re
import subprocess
import sys
from translations import translate as t

HELPER = '/usr/local/libexec/omarchy-reboot-macos-helper'

def detect_macos(volumes):
    matches = [v for v in volumes if re.match(r'^(?:macos\b|macintosh\b|mac os\b)', v['name'], re.I)]
    return matches[0] if len(matches) == 1 else None

def select_volume(volumes):
    detected = detect_macos(volumes)
    if detected:
        return detected
    # Labels do not prove OS identity. Let the user identify a custom name.
    options = [f"{v['index']}) {v['name']}" for v in volumes]
    result = subprocess.run(['gum', 'choose', '--no-show-help', '--header', t('picker'), '--', *options], text=True, capture_output=True)
    if result.returncode:
        return None
    for volume, label in zip(volumes, options):
        if result.stdout.rstrip('\n') == label:
            return volume
    raise ValueError('No valid boot volume selected.')

def main():
    result = subprocess.run(['sudo', '-n', HELPER, '--list'], check=True, text=True, capture_output=True)
    volumes = json.loads(result.stdout)
    volume = select_volume(volumes)
    if volume is None:
        return 130
    prompt = t("confirm", volume["name"])
    if subprocess.run(['gum', 'confirm', '--no-show-help', '--affirmative', t('yes'), '--negative', t('no'), prompt]).returncode:
        return 130
    # Recheck the list immediately before using its index; refuse a stale choice.
    latest = subprocess.run(['sudo', '-n', HELPER, '--list'], check=True, text=True, capture_output=True)
    if json.loads(latest.stdout) != volumes:
        raise ValueError('Boot volumes changed. Open the menu action again.')
    subprocess.run(['sudo', '-n', HELPER, '--select-next', str(volume['index'])], check=True)
    subprocess.run(['omarchy', 'system', 'reboot'], check=True)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError) as error:
        print(t('failed'), file=sys.stderr)
        print(f'Details: {error}', file=sys.stderr)
        sys.exit(1)
