from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import lifecycle
import menu_install
import menu_state
from install_fixture import InstallationFixture

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = InstallationFixture();self.addCleanup(self.fixture.close)
    def assert_clean_rollback(self):
        f=self.fixture
        self.assertEqual(f.menu.read_bytes(),f.initial_menu)
        self.assertFalse(f.transaction.exists())
        self.assertFalse((f.config/'omarchy'/menu_install.SNAPSHOT).exists())
    def test_invalid_staged_rule_changes_nothing(self):
        f=self.fixture;before=f.files()
        f.fail_command=lambda args:args[:2]==('/usr/bin/visudo','-cf')
        with self.assertRaises(subprocess.CalledProcessError):f.install()
        self.assertEqual(f.files(),before);self.assert_clean_rollback()
    def test_partial_privileged_write_restores_absence(self):
        f=self.fixture;original=lifecycle.write_root;failed=False
        def write(path,*args,**kwargs):
            nonlocal failed
            original(path,*args,**kwargs)
            if path==f.helper and not failed:
                failed=True;raise OSError('Injected write failure')
        with patch.object(lifecycle,'write_root',side_effect=write):
            with self.assertRaises(OSError):f.install()
        self.assertEqual(f.files(),{})
        self.assert_clean_rollback()
    def test_menu_failure_restores_both_sides(self):
        f=self.fixture;f.fail_menu='install'
        with self.assertRaises(OSError):f.install()
        self.assertEqual(f.files(),{});self.assert_clean_rollback()
    def test_watcher_activation_failure_restores_exact_files_and_state(self):
        f=self.fixture;f.seed_old_install();before=f.files()
        f.fail_command=lambda args:args[:2]==('/usr/bin/systemctl','enable')
        with self.assertRaises(subprocess.CalledProcessError):f.install()
        self.assertEqual(f.files(),before)
        self.assertTrue(f.enabled);self.assertFalse(f.active)
        self.assert_clean_rollback()
    def test_failed_menu_write_restores_ownership_snapshot(self):
        f=self.fixture;original=menu_state.atomic_write
        def write(path,text):
            if path==f.menu:raise OSError('Injected menu write failure')
            original(path,text)
        with patch.object(menu_state,'atomic_write',side_effect=write):
            with self.assertRaises(OSError):f.install()
        self.assertEqual(f.files(),{});self.assert_clean_rollback()
    def test_interrupted_rollback_can_be_retried(self):
        f=self.fixture;f.seed_old_install();before=f.files();real=lifecycle.recover_installation
        f.fail_menu='install';calls=0
        def recover():
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Simulated interruption during rollback')
            return real()
        with patch.object(lifecycle,'recover_installation',side_effect=recover):
            with self.assertRaises(OSError):f.install()
        self.assertTrue((f.transaction/'journal.json').exists())
        real()
        self.assertEqual(f.files(),before);self.assert_clean_rollback()
    def test_success_removes_all_transaction_snapshots(self):
        f=self.fixture;f.install()
        self.assertTrue(f.helper.exists());self.assertTrue(f.enabled and f.active)
        self.assertFalse(f.transaction.exists())
        self.assertFalse((f.config/'omarchy'/menu_install.SNAPSHOT).exists())
    def test_committed_install_is_not_rolled_back_on_retry(self):
        f=self.fixture;real=lifecycle.user_menu
        def menu(stage,operation,record):
            if operation=='commit':raise OSError('Simulated crash during finalization')
            return real(stage,operation,record)
        with patch.object(lifecycle,'user_menu',side_effect=menu):
            with self.assertRaises(OSError):f.install()
        before=f.files();lifecycle.recover_installation()
        self.assertEqual(f.files(),before)
        self.assertFalse(f.transaction.exists())
