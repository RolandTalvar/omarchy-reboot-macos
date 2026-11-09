import json
import threading
import unittest
from unittest.mock import patch
import menu_install
import menu_state
from install_fixture import InstallationFixture

class MenuTransactionTests(unittest.TestCase):
    def setUp(self):
        self.f=InstallationFixture();self.addCleanup(self.f.close);self.root=self.f.config/'omarchy'
    def test_rollback_retains_unrelated_edits_made_after_install(self):
        menu_install.install(self.root)
        data=menu_state.read_menu(self.f.menu);data['personal.new']={'label':'New notes'}
        self.f.menu.write_text(json.dumps(data));menu_install.rollback(self.root)
        data=menu_state.read_menu(self.f.menu)
        self.assertEqual(data['personal.new'],{'label':'New notes'})
        self.assertEqual(data['system.shutdown']['action'],'my-save-and-shutdown')
        self.assertNotIn('system.reboot-macos',data)
    def test_rollback_never_replaces_the_lock_inode(self):
        menu_install.install(self.root)
        lock=self.root/'.reboot-macos-menu.lock';inode=lock.stat().st_ino
        with menu_state.locked(self.root):menu_install.rollback(self.root)
        self.assertEqual(lock.stat().st_ino,inode)
    def test_rollback_waits_for_existing_menu_lock(self):
        menu_install.install(self.root);started=threading.Event();finished=threading.Event()
        def rollback():started.set();menu_install.rollback(self.root);finished.set()
        with menu_state.locked(self.root):
            thread=threading.Thread(target=rollback);thread.start();self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.05))
        thread.join(2);self.assertFalse(thread.is_alive());self.assertTrue(finished.is_set())
    def test_failed_partial_install_rolls_back_under_same_lock(self):
        original=menu_state.atomic_write
        def fail(path,value):
            if path==self.f.menu:raise OSError('Interrupted menu write')
            original(path,value)
        with patch.object(menu_state,'atomic_write',side_effect=fail):
            with self.assertRaises(OSError):menu_install.install(self.root)
        self.assertEqual(self.f.menu.read_bytes(),self.f.initial_menu)
        self.assertFalse((self.root/'reboot-macos-menu-state.json').exists())
