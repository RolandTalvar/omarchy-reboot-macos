"""Transactional ownership of this plugin's menu changes, including removal."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import threading

ID = 'rolandtlvr.reboot-macos'
KEYS = ['system.reboot-macos', 'system.shutdown', 'system.shutdown-last']

def strip_jsonc(text):
    # Preserve positions while stripping comments, then trailing commas. Both
    # passes track string escapes so command arguments are never rewritten.
    chars=list(text);quoted=escape=False;index=0
    while index<len(chars):
        ch=chars[index]
        if quoted:
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
        elif ch=='"':quoted=True
        elif ch=='/' and index+1<len(chars) and chars[index+1]=='/':
            while index<len(chars) and chars[index]!='\n':chars[index]=' ';index+=1
            continue
        index+=1
    quoted=escape=False
    for index,ch in enumerate(chars):
        if quoted:
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
        elif ch=='"':quoted=True
        elif ch==',':
            following=index+1
            while following<len(chars) and chars[following].isspace():following+=1
            if following<len(chars) and chars[following] in '}]':chars[index]=' '
    return ''.join(chars)


def menu_value(value):
    # Omarchy's older menu parser uses a string-unaware trailing-comma regex.
    # Escape commas in values we emit so it cannot alter a shell argument.
    raw=json.dumps(value,ensure_ascii=False);result=[];quoted=escape=False
    for ch in raw:
        result.append('\\u002c' if quoted and ch==',' else ch)
        if escape:escape=False
        elif quoted and ch=='\\':escape=True
        elif ch=='"':quoted=not quoted
    return ''.join(result)


def parse_menu(text):
    text=strip_jsonc(text)
    return json.loads(text) if text.strip() else {}

def read_menu(path): return parse_menu(path.read_text()) if path.exists() else {}
def items(data): return data.get('items', data)

def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        if path.exists(): os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, 'w') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)

def write_json(path, data): atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')

_held_locks = threading.local()

@contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    key = str(root.resolve())
    held = getattr(_held_locks, 'roots', set())
    if key in held:
        yield
        return
    with (root / '.reboot-macos-menu.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _held_locks.roots = held | {key}
        try: yield
        finally: _held_locks.roots = held

def paths(root): return root / 'extensions/omarchy-menu.jsonc', root / 'reboot-macos-menu-state.json'

def install_menu(root, strings, stock_shutdown=None):
    menu, state_path = paths(root)
    with locked(root):
        data = read_menu(menu)
        rows = items(data)
        if state_path.exists():
            # Idempotent setup: never replace the original backup with our rows.
            return
        original = menu.read_text() if menu.exists() else ''
        before = {key: deepcopy(rows.get(key)) for key in KEYS}
        legacy = root / 'reboot-macos-menu-backup.json'
        if legacy.exists() and (rows.get(KEYS[0]) or {}).get('action') == f'omarchy-shell {ID} reboot':
            # v0.1/0.2 could back up our pre-plugin local customization. Retire
            # exactly that known customization; retain genuine custom values.
            old = json.loads(legacy.read_text())
            if (old.get(KEYS[0]) or {}).get('action') == 'omarchy-launch-floating-terminal-with-presentation bash ~/.config/omarchy/scripts/restart-macos':
                before = {key: None for key in KEYS}
            else:
                before = {key: old.get(key) for key in KEYS}
            original = None  # restore per-row after migrating the older schema
        elif any(rows.get(key) is not None for key in [KEYS[0], KEYS[2]]):
            raise ValueError('A menu action already uses this plugin’s row IDs. Resolve the conflict before installation.')
        effective = deepcopy(stock_shutdown or {'icon':'󰐥','label':strings['menu.shutdown'],'action':'omarchy-system shutdown'})
        effective.update(before[KEYS[1]] or {})
        custom_shutdown_label = bool(before[KEYS[1]] and 'label' in before[KEYS[1]])
        rows[KEYS[0]] = {'icon':'󰀵','label':strings['menu.label'],'description':strings['menu.description'],
            'searchTerms':['Reboot into macOS'], 'when':f'omarchy-shell {ID} ping', 'action':f'omarchy-shell {ID} reboot'}
        rows[KEYS[1]] = {**(before[KEYS[1]] or {}), 'when':'false'}
        rows[KEYS[2]] = effective
        state = {'version':1, 'before':before, 'applied':{key:deepcopy(rows[key]) for key in KEYS},
            'original_text':original, 'original_existed':menu.exists(), 'custom_shutdown_label':custom_shutdown_label}
        # State first: a crash before menu writing is still reversible.
        text = patch_rows(menu.read_text() if menu.exists() else '', {key:rows[key] for key in KEYS})
        state['last_text'] = text
        write_json(state_path,state)
        atomic_write(menu,text)
        legacy.unlink(missing_ok=True)

def sync_strings(root, strings):
    menu, state_path = paths(root)
    if not state_path.exists(): return False
    with locked(root):
        if not menu.exists() or not state_path.exists(): return False
        data, state = read_menu(menu), json.loads(state_path.read_text())
        rows = items(data)
        row = rows.get(KEYS[0],{})
        applied = state['applied']
        if row.get('action') != applied[KEYS[0]].get('action'): return False
        changed = False
        for key, fields in [(KEYS[0],{'label':strings['menu.label'],'description':strings['menu.description']}),
                            (KEYS[2], {} if state['custom_shutdown_label'] else {'label':strings['menu.shutdown']})]:
            current = rows.get(key,{})
            for field,value in fields.items():
                if current.get(field) == applied[key].get(field) and current.get(field) != value:
                    current[field] = value
                    applied[key][field] = value
                    changed = True
        if changed:
            text = patch_rows(menu.read_text(),{key:rows[key] for key in KEYS if key in rows})
            state['last_text'] = text
            write_json(state_path,state)
            atomic_write(menu,text)
        return changed

def remove_menu(root):
    menu,state_path = paths(root)
    with locked(root):
        if not state_path.exists(): return False
        state = json.loads(state_path.read_text())
        if not menu.exists():
            state_path.unlink()
            return True
        data = read_menu(menu)
        rows = items(data)
        clean = all(rows.get(key) == state['applied'][key] for key in KEYS)
        if clean and state['original_text'] is not None and menu.read_text() == state.get('last_text'):
            # Restore bytes, including comments, when nothing else changed.
            expected = parse_menu(state['original_text'])
            remaining = deepcopy(data)
            remrows = items(remaining)
            for key in KEYS:
                previous = state['before'][key]
                if previous is None: remrows.pop(key,None)
                else: remrows[key] = previous
            if remaining == expected:
                if state['original_existed']: atomic_write(menu,state['original_text'])
                else: menu.unlink(missing_ok=True)
                state_path.unlink()
                return True
        for key in KEYS:
            current,applied,previous = rows.get(key),state['applied'][key],state['before'][key]
            if current == applied:
                if previous is None: rows.pop(key,None)
                else: rows[key] = previous
            elif isinstance(current,dict):
                if previous is None and applied.get('action') is not None and current.get('action') == applied['action']:
                    rows.pop(key,None)  # Our newly introduced command, not a user replacement.
                else:
                    for field,value in applied.items():
                        if current.get(field) == value:
                            if previous is not None and field in previous: current[field] = previous[field]
                            else: current.pop(field,None)
                    if not current: rows.pop(key,None)
        atomic_write(menu,patch_rows(menu.read_text(),{key:rows.get(key) for key in KEYS}))
        state_path.unlink()
        return True

# Surgical edits preserve unrelated JSONC comments and formatting. Omarchy
# accepts trailing commas, which also makes last-row deletion non-destructive.
def patch_rows(text, changes):
    text = text or '{}\n'
    if not strip_jsonc(text).strip():
        text = text.rstrip() + '\n{}\n'
    def skip(pos):
        while pos < len(text):
            if text[pos].isspace(): pos += 1
            elif text.startswith('//',pos):
                end=text.find('\n',pos);pos=len(text) if end<0 else end+1
            else:break
        return pos
    def value_end(pos):
        stack=[];quoted=False;escape=False;last=pos
        while pos<len(text):
            ch=text[pos]
            if quoted:
                if escape:escape=False
                elif ch=='\\':escape=True
                elif ch=='"':quoted=False
                last=pos+1
            elif ch=='"':quoted=True
            elif text.startswith('//',pos):
                end=text.find('\n',pos);pos=len(text) if end<0 else end
                continue
            elif ch in '[{':stack.append(ch)
            elif ch in ']}':
                if not stack:return pos,last
                stack.pop()
            elif ch==',' and not stack:return pos,last
            if not ch.isspace(): last=pos+1
            pos+=1
        raise ValueError('Incomplete JSONC value')
    def properties(start):
        pos=skip(start)
        if pos>=len(text) or text[pos]!='{':raise ValueError('Expected a menu object')
        pos+=1;result=[]
        while True:
            pos=skip(pos)
            if pos>=len(text):raise ValueError('Incomplete menu object')
            if text[pos]=='}':return result,pos
            key_start=pos
            key,size=json.JSONDecoder().raw_decode(text[pos:])
            pos=skip(pos+size)
            if not isinstance(key,str) or pos>=len(text) or text[pos]!=':':raise ValueError('Invalid menu property')
            val_start=skip(pos+1);end,val_end=value_end(val_start)
            comma=end if text[end]==',' else None
            result.append((key,key_start,val_start,val_end,comma))
            pos=end+1 if comma is not None else end
    spans,close=properties(0)
    wrapped=next((span for span in spans if span[0]=='items'),None)
    if wrapped:spans,close=properties(wrapped[2])
    edits=[];existing={span[0] for span in spans}
    for key,start,val_start,val_end,comma in spans:
        if key not in changes:continue
        value=changes[key]
        if value is None:
            edits.append((start,comma+1 if comma is not None else val_end,''))
        else:edits.append((val_start,val_end,menu_value(value)))
    additions=[(key,value) for key,value in changes.items() if key not in existing and value is not None]
    if additions:
        remaining=[span for span in spans if changes.get(span[0],{}) is not None]
        prefix = ''
        if remaining and remaining[-1][4] is None:
            if remaining[-1][3] == close: prefix = ','
            else: edits.append((remaining[-1][3],remaining[-1][3],','))
        rows=',\n'.join('  '+json.dumps(key)+': '+menu_value(value) for key,value in additions)
        edits.append((close,close,prefix+'\n'+rows+'\n'))
    for start,end,value in sorted(edits,reverse=True):text=text[:start]+value+text[end:]
    parse_menu(text)  # refuse an invalid result before touching the file
    return text

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != 'remove': raise SystemExit('Usage: menu_state.py remove CONFIG_HOME')
    root = Path(sys.argv[2]) / 'omarchy'
    remove_menu(root)

