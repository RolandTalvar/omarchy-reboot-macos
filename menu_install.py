#!/usr/bin/python3 -I
"""User-privilege setup with a stable lock and merge-aware rollback."""
import base64
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from menu_state import atomic_write, install_menu, read_menu, write_json, locked, parse_menu, patch_rows, items, KEYS
from translations import translate

SNAPSHOT = 'reboot-macos-install-transaction.json'
FILES = ['extensions/omarchy-menu.jsonc', 'reboot-macos-menu-state.json',
         'reboot-macos-menu-backup.json']
MISSING = object()

def discard(path):
    if not path.exists() and not path.is_symlink(): return
    path.unlink()
    descriptor=os.open(path.parent,os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def capture(root):
    saved = {}
    for name in FILES:
        path = root/name
        if path.is_symlink(): raise ValueError('Refusing a symlinked menu or state file.')
        saved[name] = ({'data':base64.b64encode(path.read_bytes()).decode(),
                        'mode':path.stat().st_mode & 0o777} if path.exists() else None)
    return saved

def text(value): return base64.b64decode(value['data']).decode('utf-8') if value else ''

def begin(root):
    with locked(root):
        snapshot=root/SNAPSHOT
        if snapshot.exists(): raise ValueError('An unfinished menu transaction needs recovery first.')
        write_json(snapshot,{'version':2,'before':capture(root),'applied':None})

def undo(before, applied, current):
    if before == applied or current == before: return current
    if current == applied: return before
    if isinstance(current,dict) and (isinstance(before,dict) or before is MISSING) and (isinstance(applied,dict) or applied is MISSING):
        result=dict(current);a={} if before is MISSING else before;b={} if applied is MISSING else applied
        for key in a.keys() | b.keys():
            value=undo(a.get(key,MISSING),b.get(key,MISSING),current.get(key,MISSING))
            if value is MISSING: result.pop(key,None)
            else: result[key]=value
        return result
    return current  # A later edit wins over our rollback.

def infer_applied(root,before):
    expected=dict(before)
    state=root/FILES[1]
    if state.exists() and capture(root)[FILES[1]] != before[FILES[1]]:
        data=json.loads(state.read_text())
        if 'last_text' not in data: raise ValueError('Cannot infer an interrupted menu write safely.')
        expected[FILES[0]]={'data':base64.b64encode(data['last_text'].encode()).decode(),
                            'mode':(before[FILES[0]] or {'mode':0o600})['mode']}
        expected[FILES[1]]=capture(root)[FILES[1]]
        expected[FILES[2]]=None
    return expected

def rollback(root):
    with locked(root):
        snapshot=root/SNAPSHOT
        if not snapshot.exists(): return
        payload=json.loads(snapshot.read_text())
        before=payload.get('before',payload)  # Older snapshot schema.
        applied=payload.get('applied') or infer_applied(root,before)
        current=capture(root)
        # Prepare every result before writing anything. Invalid manual edits
        # stop recovery instead of being silently replaced by an old file.
        results={}
        for name in FILES:
            a,b,c=before[name],applied[name],current[name]
            if a==b or c==a: continue
            if c==b: results[name]=a
            elif name==FILES[0] and c is not None:
                original=parse_menu(text(a));installed=parse_menu(text(b));now=parse_menu(text(c))
                merged=undo(original,installed,now)
                for key in [KEYS[0],KEYS[2]]:
                    introduced=items(installed).get(key,{})
                    current_row=items(now).get(key,{})
                    if key not in items(original) and introduced.get('action') is not None and current_row.get('action')==introduced['action']:
                        items(merged).pop(key,None)
                changes={key:items(merged).get(key) for key in KEYS
                         if items(original).get(key)!=items(installed).get(key)}
                value=patch_rows(text(c),changes)
                results[name]={'data':base64.b64encode(value.encode()).decode(),'mode':c['mode']}
            elif name==FILES[1] and a is None:
                results[name]=None  # State owned exclusively by this failed install.
        for name,value in results.items():
            path=root/name
            if value is None: discard(path)
            else:
                atomic_write(path,text(value));path.chmod(value['mode'])
                with path.open('rb') as restored: os.fsync(restored.fileno())
        discard(snapshot)

def commit(root):
    with locked(root): discard(root/SNAPSHOT)

def install(root):
    with locked(root):
        begin(root)
        try:
            os.environ['XDG_CONFIG_HOME']=str(root.parent)
            os.environ['OMARCHY_LANGUAGE_FILE']=str(root/'language')
            strings={key:translate(key) for key in ['menu.label','menu.description','menu.shutdown']}
            stock_path=Path('/usr/share/omarchy/default/omarchy/omarchy-menu.jsonc')
            stock=read_menu(stock_path).get('system.shutdown') if stock_path.exists() else None
            if stock: stock['label']=strings['menu.shutdown']
            install_menu(root,strings,stock)
            saved=json.loads((root/SNAPSHOT).read_text());saved['applied']=capture(root)
            write_json(root/SNAPSHOT,saved)
        except BaseException:
            rollback(root)
            raise

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1] not in ['install','rollback','commit']:
        raise SystemExit('Usage: menu_install.py install|rollback|commit CONFIG_HOME')
    {'install':install,'rollback':rollback,'commit':commit}[sys.argv[1]](Path(sys.argv[2])/'omarchy')
