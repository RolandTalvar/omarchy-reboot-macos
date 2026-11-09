#!/usr/bin/python3
"""Detect macOS from APFS metadata and queue a recoverable reboot."""
import json
import os
from pathlib import Path
import subprocess
import sys
from translations import translate as t

HELPER = '/usr/local/libexec/omarchy-reboot-macos-helper'

def detect_macos(volumes):
    matches = [v for v in volumes if v.get('os') == 'macos' and v.get('selectable', False)]
    return matches[0] if len(matches) == 1 else None

def select_volume(volumes):
    detected = detect_macos(volumes)
    if detected:
        return detected
    # Labels do not prove OS identity. Let the user identify a custom name.
    volumes = [v for v in volumes if v.get('selectable', False)]
    if not volumes: raise ValueError('No uniquely selectable boot volume is available.')
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
    return queue_reboot(volumes, volume)

def queue_reboot(volumes, volume):
    # Recheck the snapshot after confirmation; refuse a stale choice.
    latest = subprocess.run(['sudo', '-n', HELPER, '--list'], check=True, text=True, capture_output=True)
    if json.loads(latest.stdout) != volumes:
        raise ValueError('Boot volumes changed. Open the menu action again.')
    subprocess.run(['sudo', '-n', HELPER, '--select-next', volume['id']], check=True)
    # Run the reboot in a detached user unit. Omarchy closes all windows, so
    # recovery must survive the confirmation terminal being closed.
    try:
        subprocess.run(['systemd-run', '--user', '--collect', '--quiet',
                    '--property=Type=exec', '--setenv=PATH', '--setenv=OMARCHY_PATH', '--setenv=HYPRLAND_INSTANCE_SIGNATURE', '/usr/bin/python3', '-B',
                    str(Path(__file__).resolve()), '--reboot-worker', volume['id']], check=True)
    except (OSError, subprocess.CalledProcessError):
        recover_selection(volume['id'])
        raise
    return 0

def reboot_worker(selected_id):
    try:
        # --execute is synchronous: the ordinary command only queues another
        # unit, which would conceal a subsequent reboot failure from us.
        subprocess.run(['omarchy', 'system', 'reboot', '--execute'], check=True)
        return 0
    except (OSError, subprocess.CalledProcessError) as error:
        recover_selection(selected_id)
        print(f'Details: {error}', file=sys.stderr)
        return 1

def recover_selection(selected_id):
    try:
        subprocess.run(['sudo', '-n', HELPER, '--clear-next', selected_id], check=True)
        message = t('recovery.cleared')
    except (OSError, subprocess.CalledProcessError):
        message = t('recovery.pending')
    print(message, file=sys.stderr)
    subprocess.run(['omarchy-notification-send', '-u', 'critical', t('failed'), message], check=False)

def dispatch(args):
    if args == ['--list']:
        result = subprocess.run(['sudo','-n',HELPER,'--list'],check=True,text=True,capture_output=True)
        print(result.stdout, end='')
        return 0
    if len(args) == 3 and args[0] == '--confirmed':
        selected_id, snapshot = args[1], json.loads(args[2])
        matches = [v for v in snapshot if v.get('id') == selected_id and v.get('selectable')]
        if len(matches) != 1: raise ValueError('Invalid confirmed boot volume')
        return queue_reboot(snapshot, matches[0])
    if len(args) == 2 and args[0] == '--reboot-worker': return reboot_worker(args[1])
    if args: raise ValueError('Invalid reboot operation')
    return main()

if __name__ == '__main__':
    try:
        sys.exit(dispatch(sys.argv[1:]))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(t('failed'), file=sys.stderr)
        print(f'Details: {error}', file=sys.stderr)
        sys.exit(1)
