#!/usr/bin/python3
"""Explicit one-time setup; plugin loading never mutates menu files."""
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys

ID = 'rolandtlvr.reboot-macos'
KEYS = ['system.reboot-macos', 'system.shutdown', 'system.shutdown-last']

def read_menu(path):
    if not path.exists():
        return {}
    text = re.sub(r'^\s*//[^\n]*(\n|$)', '', path.read_text(), flags=re.M)
    return json.loads(re.sub(r',\s*([}\]])', r'\1', text))

def main():
    if sys.argv[1:] not in [['install'], ['remove']]:
        raise SystemExit('Usage: python3 setup.py install|remove')
    mode = sys.argv[1]
    source = Path(__file__).resolve().parent
    root = Path.home() / '.config/omarchy'
    menu = root / 'extensions/omarchy-menu.jsonc'
    state = root / 'reboot-macos-menu-backup.json'
    data = read_menu(menu)
    items = data.setdefault('items', {}) if 'items' in data else data
    # Read and preserve existing entries before requesting administrator rights.
    previous = {key: items.get(key) for key in KEYS}
    subprocess.run(['pkexec', '/bin/bash', str(source / 'setup-root'), mode, pwd.getpwuid(os.getuid()).pw_name], check=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    menu.parent.mkdir(parents=True, exist_ok=True)
    if menu.exists():
        shutil.copy2(menu, str(menu) + '.bak.' + stamp)
    if mode == 'install':
        if not state.exists():
            state.write_text(json.dumps(previous, indent=2) + '\n')
        items['system.reboot-macos'] = {
            'icon': '󰀵', 'label': 'Reboot into macOS',
            'description': 'Boot macOS once; keep Linux as the default',
            'when': f'omarchy-shell {ID} ping',
            'action': f'omarchy-shell {ID} reboot',
        }
        # User entries append after stock entries: move Shutdown after ours.
        items['system.shutdown'] = {'when': 'false'}
        items['system.shutdown-last'] = {'icon': '󰐥', 'label': 'Shutdown', 'action': 'omarchy-system shutdown'}
    else:
        # Remove our rows and restore stock Shutdown. Never restore the obsolete
        # machine-specific reboot action whose privilege rule was retired.
        previous = json.loads(state.read_text()) if state.exists() else {}
        for key in KEYS:
            value = previous.get(key)
            if key in ['system.reboot-macos', 'system.shutdown-last']:
                value = None
            if key == 'system.shutdown' and value == {'when': 'false'}:
                value = None
            if value is None:
                items.pop(key, None)
            else:
                items[key] = value
        state.unlink(missing_ok=True)
    menu.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    print(f'Menu and privileged helper {mode} complete.')

if __name__ == '__main__':
    main()
