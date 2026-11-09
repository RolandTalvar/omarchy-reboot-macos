#!/usr/bin/python3
"""Update only owned labels through the shared menu transaction code."""
import json
import os
from pathlib import Path
import sys
from menu_state import sync_strings

def sync_menu(path, strings):
    return sync_strings(path.parent.parent, strings)

if __name__ == '__main__':
    strings = json.loads(sys.argv[1])
    for key in ['menu.label','menu.description','menu.shutdown']:
        if not isinstance(strings.get(key),str) or not 0 < len(strings[key]) <= 4096:
            raise ValueError('Invalid translated menu label')
    config = Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    sync_strings(config/'omarchy',strings)
