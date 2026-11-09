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
