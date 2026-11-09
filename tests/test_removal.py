import json
from pathlib import Path
import unittest
from unittest.mock import patch
import lifecycle
import menu_state
from install_fixture import InstallationFixture

class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.f=InstallationFixture();self.addCleanup(self.f.close);self.f.install()
        delegate=self.f.run
        def run(*args,**kwargs):
            if args[0]=='/usr/bin/runuser':menu_state.remove_menu(self.f.config/'omarchy')
            if args[:2]==('/usr/bin/systemctl','disable') and not (self.f.units/(lifecycle.UNIT+'.path')).exists():
                raise RuntimeError('Cannot disable a missing unit')
            return delegate(*args,**kwargs)
        patched=patch.object(lifecycle,'run',side_effect=run);patched.start();self.addCleanup(patched.stop)
    def remove(self):lifecycle.remove({'account':'user','config':str(self.f.config)})
    def test_retry_after_each_file_deletion_is_idempotent(self):
        for target in [self.f.rule,self.f.helper,self.f.units/(lifecycle.UNIT+'.path'),self.f.record]:
            with self.subTest(target=target):
                if not self.f.record.exists():self.f.install()
                original=Path.unlink;failed=False
                def unlink(path,*args,**kwargs):
                    nonlocal failed
                    result=original(path,*args,**kwargs)
                    if path==target and not failed:failed=True;raise OSError('Interrupted removal')
                    return result
                with patch.object(Path,'unlink',unlink):
                    with self.assertRaises(OSError):self.remove()
                self.remove()
                self.assertFalse(self.f.rule.exists());self.assertFalse(self.f.helper.exists())
                self.assertFalse(self.f.record.exists());self.assertFalse(self.f.lib.exists())
    def test_invalid_menu_does_not_leave_passwordless_access(self):
        good=self.f.menu.read_text();self.f.menu.write_text('broken')
        with self.assertRaises(ValueError):self.remove()
        self.assertFalse(self.f.rule.exists());self.assertFalse(self.f.helper.exists())
        self.assertTrue((self.f.lib/'lifecycle.py').exists());self.assertTrue(self.f.record.exists())
        self.f.menu.write_text(good);self.remove()
        self.assertEqual(self.f.menu.read_bytes(),self.f.initial_menu)
    def test_cleanup_service_retries_failed_restoration(self):
        text=(self.f.units/(lifecycle.UNIT+'.service')).read_text()
        self.assertIn('Restart=on-failure',text);self.assertIn('RestartSec=15s',text)

    def test_known_legacy_rules_are_revoked_on_removal(self):
        for command in ['--set-boot macOS Sequoia','--set-boot-macos']:
            if not self.f.record.exists():self.f.install()
            self.f.legacy.write_text('user ALL=(root) NOPASSWD: /usr/bin/asahi-bless --next '+command+' --yes\n')
            self.remove();self.assertFalse(self.f.legacy.exists())
    def test_unknown_administrator_rule_is_not_deleted(self):
        self.f.legacy.write_text('# administrator managed rule\n')
        self.remove();self.assertEqual(self.f.legacy.read_text(),'# administrator managed rule\n')
    def test_legacy_rule_is_revoked_without_an_installation_record(self):
        self.f.record.unlink()
        self.f.legacy.write_text('user ALL=(root) NOPASSWD: /usr/bin/asahi-bless --next --set-boot-macos --yes\n')
        lifecycle.remove_for_account('user',str(self.f.config))
        self.assertFalse(self.f.legacy.exists())

    def test_damaged_recovery_journals_cannot_block_revocation(self):
        self.f.transaction.mkdir(parents=True)
        for name in ['journal.json','journal.mirror.json']:(self.f.transaction/name).write_text('')
        with self.assertRaises(lifecycle.RecoveryError):lifecycle.remove_for_account('user',str(self.f.config))
        self.assertFalse(self.f.rule.exists());self.assertFalse(self.f.helper.exists())
    def test_failed_menu_rollback_cannot_restore_revoked_access_on_retry(self):
        f=self.f;f.fail_menu='install';real=lifecycle.recover_installation;calls=0
        def interrupt():
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Interrupted rollback')
            return real()
        with patch.object(lifecycle,'recover_installation',side_effect=interrupt):
            with self.assertRaises(OSError):f.install()
        delegate=f.user_menu
        def fail_menu(stage,operation,record):
            if operation=='rollback':raise ValueError('Invalid edited menu')
            return delegate(stage,operation,record)
        with patch.object(lifecycle,'user_menu',side_effect=fail_menu):
            for attempt in range(2):
                with self.assertRaises(ValueError):lifecycle.remove_for_account('user',str(f.config))
                self.assertFalse(f.rule.exists());self.assertFalse(f.helper.exists())
                self.assertEqual(lifecycle.read_journal()['phase'],'restored')
