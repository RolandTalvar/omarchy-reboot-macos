#!/usr/bin/python3 -I
"""User-privilege half of setup, with a recoverable exact-file snapshot."""
import base64
import json
import os
from pathlib import Path
import sys

# This file is run from an administrator-owned staging or installation folder.
# Isolated Python otherwise excludes that folder from imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from menu_state import atomic_write, install_menu, read_menu, write_json
from translations import translate

SNAPSHOT = 'reboot-macos-install-transaction.json'
FILES = ['extensions/omarchy-menu.jsonc', 'reboot-macos-menu-state.json',
         'reboot-macos-menu-backup.json', '.reboot-macos-menu.lock']

def begin(root):
    snapshot = root / SNAPSHOT
    if snapshot.exists():
        raise ValueError('An unfinished menu transaction needs recovery first.')
    saved = {}
    for name in FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError('Refusing to replace a symlinked menu or state file.')
        saved[name] = ({'data': base64.b64encode(path.read_bytes()).decode(),
                        'mode': path.stat().st_mode & 0o777}
                       if path.exists() else None)
    write_json(snapshot, saved)
    snapshot.chmod(0o600)

def rollback(root):
    snapshot = root / SNAPSHOT
    if not snapshot.exists():
        return
    saved = json.loads(snapshot.read_text())
    for name in FILES:
        path = root / name
        value = saved[name]
        if value is None:
            path.unlink(missing_ok=True)
        else:
            # Config/state are UTF-8; atomic_write preserves complete files.
            atomic_write(path, base64.b64decode(value['data']).decode('utf-8'))
            path.chmod(value['mode'])
    snapshot.unlink()

def commit(root):
    (root / SNAPSHOT).unlink(missing_ok=True)

def install(root):
    begin(root)
    try:
        # Always use the desktop user's selected config, never root's language.
        os.environ['XDG_CONFIG_HOME'] = str(root.parent)
        os.environ['OMARCHY_LANGUAGE_FILE'] = str(root / 'language')
        strings = {key: translate(key) for key in
                   ['menu.label', 'menu.description', 'menu.shutdown']}
        stock_path = Path('/usr/share/omarchy/default/omarchy/omarchy-menu.jsonc')
        stock = read_menu(stock_path).get('system.shutdown') if stock_path.exists() else None
        if stock:
            stock['label'] = strings['menu.shutdown']
        install_menu(root, strings, stock)
    except BaseException:
        rollback(root)
        raise

if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ['install', 'rollback', 'commit']:
        raise SystemExit('Usage: menu_install.py install|rollback|commit CONFIG_HOME')
    {'install': install, 'rollback': rollback, 'commit': commit}[sys.argv[1]](
        Path(sys.argv[2]) / 'omarchy')
