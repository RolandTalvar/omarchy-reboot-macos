#!/usr/bin/python3 -I
"""Root setup and event-driven cleanup. Never run code from a removed plugin."""
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

LIB = Path('/usr/local/lib/omarchy-reboot-macos')
HELPER = Path('/usr/local/libexec/omarchy-reboot-macos-helper')
RULE = Path('/etc/sudoers.d/90-omarchy-reboot-macos-plugin')
RECORD = Path('/etc/omarchy-reboot-macos.json')
UNIT = 'omarchy-reboot-macos-cleanup'
UNITS = Path('/etc/systemd/system')
ENV = {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}

def run(*args, **kwargs): return subprocess.run(list(args),env=ENV,check=True,**kwargs)

def write_root(path,text,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as output: output.write(text)
        os.replace(temp,path)
    finally: Path(temp).unlink(missing_ok=True)

def remove(record):
    # Restore user menu while trusted code still exists; drop privileges first.
    # Failed restoration leaves the installation available for recovery.
    menu_code = LIB/'menu_state.py'
    if menu_code.exists():
        run('/usr/bin/runuser','-u',record['account'],'--','/usr/bin/python3','-I',str(menu_code),'remove',record['config'])
    run('/usr/bin/systemctl','disable','--now',UNIT+'.path')
    for suffix in ['path','service']: (UNITS/(UNIT+'.'+suffix)).unlink(missing_ok=True)
    RULE.unlink(missing_ok=True)
    HELPER.unlink(missing_ok=True)
    RECORD.unlink(missing_ok=True)
    # Only our fixed installation directory, never a supplied path.
    if LIB.exists(): shutil.rmtree(LIB)
    run('/usr/bin/systemctl','daemon-reload')
    run('/usr/bin/visudo','-c')

def install(account,config,source):
    user=pwd.getpwnam(account)
    if user.pw_uid == 0: raise ValueError('Install for a desktop user, not root')
    if RECORD.exists() and json.loads(RECORD.read_text())['account'] != account:
        raise ValueError('This helper is already installed for another user')
    config=Path(config).resolve()
    if any(ord(ch) < 32 for ch in str(config)): raise ValueError('Unsupported config path')
    plugin=config/'omarchy/plugins/rolandtlvr.reboot-macos'
    if not (plugin/'manifest.json').is_file(): raise ValueError('Install the Omarchy plugin first')
    if not Path('/usr/bin/asahi-bless').is_file(): raise ValueError('Install asahi-bless first')
    source=Path(source)
    for name in ['apfs_metadata.py','menu_state.py','lifecycle.py']:
        write_root(LIB/name,(source/name).read_text())
    write_root(HELPER,(source/'boot_helper.py').read_text(),0o755)
    rule=f'{account} ALL=(root) NOPASSWD: {HELPER} --list, {HELPER} ^--select-next [a-f0-9]{{64}}$, {HELPER} ^--clear-next [a-f0-9]{{64}}$\n'
    fd,temp=tempfile.mkstemp(prefix='.reboot-macos.',dir=RULE.parent)
    try:
        os.fchmod(fd,0o440)
        with os.fdopen(fd,'w') as output: output.write(rule)
        run('/usr/bin/visudo','-cf',temp)
        os.replace(temp,RULE)
    finally: Path(temp).unlink(missing_ok=True)
    record={'version':1,'account':account,'config':str(config),'plugin':str(plugin)}
    write_root(RECORD,json.dumps(record)+'\n')
    # Watch the parent so deleting, unlinking, or renaming a plugin triggers a
    # check. There is no timer or permanent daemon. Other plugins are ignored.
    watch=str(plugin.parent).replace('%','%%')
    write_root(UNITS/(UNIT+'.path'),f'[Unit]\nDescription=Watch for removal of the macOS reboot plugin\n\n[Path]\nPathChanged={watch}\nUnit={UNIT}.service\n\n[Install]\nWantedBy=multi-user.target\n')
    write_root(UNITS/(UNIT+'.service'),f'[Unit]\nDescription=Clean up removed macOS reboot plugin\n\n[Service]\nType=oneshot\nExecStartPre=/usr/bin/sleep 2\nExecStart=/usr/bin/python3 -I {LIB}/lifecycle.py check\n')
    legacy=Path('/etc/sudoers.d/90-omarchy-reboot-macos')
    if legacy.exists() and legacy.read_text().strip()==f'{account} ALL=(root) NOPASSWD: /usr/bin/asahi-bless --next --set-boot macOS Sequoia --yes':
        shutil.copy2(legacy,'/root/omarchy-reboot-macos-legacy-rule.bak')
        legacy.unlink()
    run('/usr/bin/visudo','-c')
    run('/usr/bin/systemctl','daemon-reload')
    run('/usr/bin/systemctl','enable','--now',UNIT+'.path')

def main(args):
    if os.geteuid()!=0: raise ValueError('Administrator authentication required')
    if args==['check']:
        if RECORD.exists():
            record=json.loads(RECORD.read_text())
            if not Path(record['plugin']).exists(): remove(record)
    elif len(args)==4 and args[0] in ['install','remove']:
        mode,account,config,source=args
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*',account): raise ValueError('Invalid account')
        if mode=='install': install(account,config,source)
        elif RECORD.exists():
            record=json.loads(RECORD.read_text())
            if record['account']!=account: raise ValueError('Installation belongs to another user')
            remove(record)
        else:
            # Compatibility cleanup for installations before the watcher.
            RULE.unlink(missing_ok=True);HELPER.unlink(missing_ok=True)
    else: raise ValueError('Invalid setup operation')

if __name__=='__main__': main(sys.argv[1:])
