"""Exercise real installation file changes under a disposable prefix."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import os
import lifecycle
import menu_install

SOURCE = Path(__file__).resolve().parents[1]

class InstallationFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root/'config'
        self.plugin = self.config/'omarchy/plugins/rolandtlvr.reboot-macos'
        self.plugin.mkdir(parents=True)
        (self.plugin/'manifest.json').write_text('{}')
        self.menu = self.config/'omarchy/extensions/omarchy-menu.jsonc'
        self.menu.parent.mkdir(parents=True)
        self.menu.write_text('// Custom config\n{"system.shutdown":{"label":"Save and power off","action":"my-save-and-shutdown"}}\n')
        self.initial_menu = self.menu.read_bytes()
        self.lib = self.root/'lib'
        self.helper = self.root/'helper'
        self.rule = self.root/'sudoers/rule'
        self.rule.parent.mkdir()
        self.record = self.root/'record'
        self.units = self.root/'units'; self.units.mkdir()
        self.transaction = self.root/'transactions/install'
        self.legacy = self.root/'sudoers/legacy'
        self.bless = self.root/'asahi-bless'; self.bless.touch()
        self.enabled = self.active = False
        self.fail_command = None
        self.fail_menu = None
        self.calls = []
        self.stack = ExitStack()
        self.stack.enter_context(patch.multiple(lifecycle, LIB=self.lib, HELPER=self.helper,
            RULE=self.rule, RECORD=self.record, UNITS=self.units, TRANSACTION=self.transaction,
            LEGACY=self.legacy, BLESS=self.bless))
        self.stack.enter_context(patch.object(lifecycle.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)))
        self.stack.enter_context(patch.object(lifecycle,'run',side_effect=self.run))
        self.stack.enter_context(patch.object(lifecycle,'watcher_state',side_effect=lambda:{'enabled':self.enabled,'active':self.active}))
        self.stack.enter_context(patch.object(lifecycle,'user_menu',side_effect=self.user_menu))
    def close(self):
        self.stack.close(); self.temp.cleanup()
    def run(self,*args,**kwargs):
        self.calls.append(args)
        if args[0] == '/usr/bin/systemctl':
            if args[1] == 'disable': self.enabled = self.active = False
            elif args[1] == 'enable':
                self.enabled = True
                if '--now' in args:self.active=True
            elif args[1] == 'start':self.active=True
        if self.fail_command and self.fail_command(args):
            self.fail_command = None
            raise subprocess.CalledProcessError(1,args)
        return subprocess.CompletedProcess(args,0,stdout='')
    def user_menu(self,stage,operation,record):
        with patch.dict(os.environ):
            {'install':menu_install.install,'rollback':menu_install.rollback,
             'commit':menu_install.commit}[operation](self.config/'omarchy')
        if self.fail_menu == operation:
            self.fail_menu = None
            raise OSError('Injected user-menu failure after '+operation)
    def install(self,source=SOURCE):
        lifecycle.install('user',str(self.config),source)
    def files(self):
        result={}
        for path in [self.lib,self.helper,self.rule,self.record,self.units,self.legacy]:
            if path.is_dir():
                for file in path.rglob('*'):
                    if file.is_file():result[str(file.relative_to(self.root))]=(file.read_bytes(),file.stat().st_mode & 0o777)
            elif path.exists():result[str(path.relative_to(self.root))]=(path.read_bytes(),path.stat().st_mode & 0o777)
        return result
    def seed_old_install(self):
        self.lib.mkdir();(self.lib/'old-module.py').write_text('# previous trusted code\n')
        self.helper.write_text('# old helper\n');self.helper.chmod(0o755)
        self.rule.write_text('# old privilege rule\n');self.rule.chmod(0o440)
        self.record.write_text(json.dumps({'account':'user','config':str(self.config),'plugin':str(self.plugin)}))
        for suffix in ['path','service']:(self.units/(lifecycle.UNIT+'.'+suffix)).write_text('# old unit\n')
        self.enabled=True;self.active=False
