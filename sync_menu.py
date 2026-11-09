#!/usr/bin/python3
"""Update only this plugin's menu labels when the display language changes."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from setup import read_menu

ID = 'rolandtlvr.reboot-macos'

def sync_menu(path, strings):
    if not path.exists():
        return False
    before = path.read_text()
    data = read_menu(path)
    items = data.get('items', data)
    row = items.get('system.reboot-macos', {})
    # Setup is explicit; never create or reclaim a removed/modified action.
    if row.get('action') != f'omarchy-shell {ID} reboot':
        return False
    row['label'] = strings['menu.label']
    row['description'] = strings['menu.description']
    shutdown = items.get('system.shutdown-last', {})
    if shutdown.get('action') == 'omarchy-system shutdown':
        shutdown['label'] = strings['menu.shutdown']
    # Keep English searchable after translating our row.
    row['searchTerms'] = ['Reboot into macOS']
    after = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if before == after:
        return False
    # Do not overwrite a concurrent manual edit observed during preparation.
    if path.read_text() != before:
        raise RuntimeError('Menu changed during translation; try again.')
    fd, temporary = tempfile.mkstemp(prefix='.reboot-macos-menu-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(after)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True

if __name__ == '__main__':
    strings = json.loads(sys.argv[1])
    for key in ['menu.label', 'menu.description', 'menu.shutdown']:
        if not isinstance(strings.get(key), str) or not 0 < len(strings[key]) <= 4096:
            raise ValueError('Invalid translated menu label.')
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    sync_menu(config / 'omarchy/extensions/omarchy-menu.jsonc', strings)
