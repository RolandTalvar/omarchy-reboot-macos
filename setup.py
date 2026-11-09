#!/usr/bin/python3
"""Explicit installation and removal of the menu and privileged components."""
import os
from pathlib import Path
import pwd
import subprocess
import sys
from menu_state import install_menu, read_menu, remove_menu, paths, items, KEYS
from translations import translate as t

ID = 'rolandtlvr.reboot-macos'

def main():
    if sys.argv[1:] not in [['install'],['remove']]: raise SystemExit('Usage: python3 setup.py install|remove')
    mode = sys.argv[1]
    source = Path(__file__).resolve().parent
    config = Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config')).resolve()
    account = pwd.getpwuid(os.getuid()).pw_name
    if mode == 'install':
        menu,state = paths(config/'omarchy')
        current = items(read_menu(menu))
        legacy = config/'omarchy/reboot-macos-menu-backup.json'
        if not state.exists() and not legacy.exists() and any(current.get(key) is not None for key in [KEYS[0],KEYS[2]]):
            raise ValueError('Existing menu row conflicts with this plugin; resolve it before setup.')
    # Root setup records its own validated config paths, not future input.
    subprocess.run(['pkexec','/usr/bin/python3','-I',str(source/'lifecycle.py'),mode,account,str(config),str(source)],check=True)
    if mode == 'install':
        strings={key:t(key) for key in ['menu.label','menu.description','menu.shutdown']}
        stock_path=Path(os.environ.get('OMARCHY_PATH','/usr/share/omarchy'))/'default/omarchy/omarchy-menu.jsonc'
        stock=read_menu(stock_path).get('system.shutdown') if stock_path.exists() else None
        if stock: stock['label']=strings['menu.shutdown']
        install_menu(config/'omarchy',strings,stock)
    else: remove_menu(config/'omarchy')
    print(f'Menu and privileged helper {mode} complete.')

if __name__ == '__main__': main()
