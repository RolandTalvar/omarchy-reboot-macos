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

    def test_rollback_preserves_a_manual_menu_deletion(self):
        menu_install.install(self.root);self.f.menu.unlink()
        menu_install.rollback(self.root)
        self.assertFalse(self.f.menu.exists())
        self.assertFalse((self.root/menu_install.SNAPSHOT).exists())
        self.assertFalse((self.root/'reboot-macos-menu-state.json').exists())

    def test_language_change_cannot_leave_partial_rows_after_rollback(self):
        menu_install.install(self.root)
        menu_state.sync_strings(self.root,{'menu.label':'Taaskäivita macOS-i','menu.description':'Üks kord','menu.shutdown':'Lülita välja'})
        menu_install.rollback(self.root)
        result=menu_state.read_menu(self.f.menu)
        self.assertNotIn('system.reboot-macos',result);self.assertNotIn('system.shutdown-last',result)
        menu_install.install(self.root)
        self.assertIn('system.reboot-macos',menu_state.read_menu(self.f.menu))
        menu_install.commit(self.root)

    def test_interrupted_stale_state_reconcile_restores_both_sides(self):
        menu_install.install(self.root);menu_install.commit(self.root)
        rows=menu_state.read_menu(self.f.menu);rows.pop('system.reboot-macos')
        self.f.menu.write_text(json.dumps(rows))
        before=menu_install.capture(self.root)
        menu_install.begin(self.root)
        menu_state.install_menu(self.root,{'menu.label':'Reboot into macOS','menu.description':'Once','menu.shutdown':'Shutdown'})
        # Simulate termination before the applied snapshot can be persisted.
        menu_install.rollback(self.root)
        self.assertEqual(menu_install.capture(self.root),before)

    def test_stale_reconcile_does_not_write_intermediate_menu(self):
        for point in ['state','menu']:
            with self.subTest(point=point):
                menu_install.install(self.root);menu_install.commit(self.root)
                rows=menu_state.read_menu(self.f.menu);rows.pop('system.reboot-macos')
                self.f.menu.write_text(json.dumps(rows));before=menu_install.capture(self.root)
                menu_install.begin(self.root);write=menu_state.atomic_write;calls=[]
                def interrupted(path,value):
                    calls.append(path)
                    if point=='state' and path==self.root/menu_install.FILES[1]:
                        raise SystemExit('Before new state')
                    if point=='menu' and path==self.f.menu:
                        raise SystemExit('After new state, before new menu')
                    return write(path,value)
                with patch.object(menu_state,'atomic_write',side_effect=interrupted):
                    with self.assertRaises(SystemExit):
                        menu_state.install_menu(self.root,{'menu.label':'macOS','menu.description':'Once','menu.shutdown':'Shutdown'})
                self.assertEqual(self.f.menu.read_bytes(),__import__('base64').b64decode(before[menu_install.FILES[0]]['data']))
                menu_install.rollback(self.root)
                self.assertEqual(menu_install.capture(self.root),before)
