from pathlib import Path
import subprocess
import os
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

    def test_privileged_modes_ignore_permissive_and_restrictive_umasks(self):
        for mask in [0o000,0o027,0o077]:
            with self.subTest(umask=oct(mask)):
                f=InstallationFixture()
                old=os.umask(mask)
                delegate=f.user_menu
                def verify_stage(stage,operation,record):
                    self.assertEqual(f.transaction.stat().st_mode & 0o777,0o711)
                    self.assertEqual(stage.stat().st_mode & 0o777,0o755)
                    self.assertEqual((stage/'i18n').stat().st_mode & 0o777,0o755)
                    self.assertEqual((f.transaction/'backup').stat().st_mode & 0o777,0o700)
                    return delegate(stage,operation,record)
                try:
                    with patch.object(lifecycle,'user_menu',side_effect=verify_stage):f.install()
                    self.assertEqual(f.lib.stat().st_mode & 0o777,0o755)
                    self.assertEqual(f.helper.stat().st_mode & 0o777,0o755)
                    self.assertEqual(f.rule.stat().st_mode & 0o777,0o440)
                finally:os.umask(old);f.close()

    def test_root_writes_sync_file_before_rename_and_directory_after(self):
        f=self.fixture;events=[];real_replace=os.replace
        def sync(fd):
            import stat
            events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        def replace(*args):events.append('rename');return real_replace(*args)
        with patch.object(os,'fsync',side_effect=sync),patch.object(os,'replace',side_effect=replace):
            lifecycle.write_root(f.root/'probe','data')
        self.assertEqual(events,['file','rename','directory'])
    def test_damaged_primary_journal_recovers_from_durable_mirror(self):
        f=self.fixture;f.seed_old_install();before=f.files();real=lifecycle.recover_installation;calls=0
        f.fail_menu='install'
        def interrupt():
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Simulated interruption')
            return real()
        with patch.object(lifecycle,'recover_installation',side_effect=interrupt):
            with self.assertRaises(OSError):f.install()
        (f.transaction/'journal.json').write_text('')
        real()
        self.assertEqual(f.files(),before);self.assert_clean_rollback()
    def test_two_damaged_journals_fail_without_deleting_installed_files(self):
        f=self.fixture;f.seed_old_install();before=f.files()
        f.transaction.mkdir(parents=True)
        for name in ['journal.json','journal.mirror.json']:(f.transaction/name).write_text('')
        with self.assertRaisesRegex(lifecycle.RecoveryError,'left untouched'):
            lifecycle.recover_installation()
        self.assertEqual(f.files(),before)

    def test_interrupted_committed_cleanup_can_resume_without_staged_code(self):
        f=self.fixture;real= lifecycle.shutil.rmtree;failed=False
        def rmtree(path,*args,**kwargs):
            nonlocal failed
            if path==f.transaction and not failed:
                failed=True;real(f.transaction/'stage');raise OSError('Interrupted cleanup')
            return real(path,*args,**kwargs)
        with patch.object(lifecycle.shutil,'rmtree',side_effect=rmtree):
            with self.assertRaises(OSError):f.install()
        before=f.files()
        self.assertFalse((f.transaction/'journal.json').exists())
        lifecycle.recover_installation()
        self.assertEqual(f.files(),before)
    def test_interrupted_rollback_cleanup_never_replays_missing_backups(self):
        f=self.fixture;f.seed_old_install();before=f.files();f.fail_menu='install'
        real=lifecycle.shutil.rmtree;failed=False
        def rmtree(path,*args,**kwargs):
            nonlocal failed
            if path==f.transaction and not failed:
                failed=True;real(f.transaction/'backup');raise OSError('Interrupted cleanup')
            return real(path,*args,**kwargs)
        with patch.object(lifecycle.shutil,'rmtree',side_effect=rmtree):
            with self.assertRaises(OSError):f.install()
        lifecycle.recover_installation()
        self.assertEqual(f.files(),before)
    def test_missing_backup_is_detected_before_any_live_artifact_is_deleted(self):
        f=self.fixture;f.seed_old_install();real=lifecycle.recover_installation;calls=0;f.fail_menu='install'
        def interrupt():
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Interrupted rollback')
            return real()
        with patch.object(lifecycle,'recover_installation',side_effect=interrupt):
            with self.assertRaises(OSError):f.install()
        lifecycle.shutil.rmtree(f.transaction/'backup/0')
        before=f.files()
        with self.assertRaisesRegex(lifecycle.RecoveryError,'missing or incomplete'):real()
        self.assertEqual(f.files(),before)

    def test_removal_during_watcher_activation_rolls_back_installation(self):
        f=self.fixture;delegate=f.run
        def run(*args,**kwargs):
            result=delegate(*args,**kwargs)
            if args[:3]==('/usr/bin/systemctl','enable','--now'):
                lifecycle.shutil.rmtree(f.plugin)
            return result
        with patch.object(lifecycle,'run',side_effect=run):
            with self.assertRaisesRegex(ValueError,'while enabling'):f.install()
        self.assertFalse(f.helper.exists());self.assertFalse(f.rule.exists())
        self.assertFalse(f.record.exists());self.assertFalse(f.enabled or f.active)
        self.assert_clean_rollback()

    def test_restored_artifacts_are_synced_before_journals_are_retired(self):
        f=self.fixture;f.seed_old_install();f.fail_menu='install';events=[]
        real_sync=lifecycle.sync_tree;real_finish=lifecycle.finish_transaction
        def sync(path):events.append(('sync',path));return real_sync(path)
        def finish():events.append(('finish',None));return real_finish()
        with patch.object(lifecycle,'sync_tree',side_effect=sync),patch.object(lifecycle,'finish_transaction',side_effect=finish):
            with self.assertRaises(OSError):f.install()
        end=events.index(('finish',None))
        self.assertIn(('sync',f.lib),events[:end]);self.assertIn(('sync',f.helper),events[:end])

    def test_failed_upgrade_cleans_old_install_if_plugin_was_removed(self):
        f=self.fixture;f.seed_old_install();f.active=True;delegate=f.run
        def run(*args,**kwargs):
            result=delegate(*args,**kwargs)
            if args[:3]==('/usr/bin/systemctl','enable','--now'):lifecycle.shutil.rmtree(f.plugin)
            return result
        with patch.object(lifecycle,'run',side_effect=run):
            with self.assertRaises(ValueError):f.install()
        self.assertFalse(f.helper.exists());self.assertFalse(f.rule.exists());self.assertFalse(f.record.exists())
    def test_watcher_stays_active_during_an_upgrade(self):
        f=self.fixture;f.seed_old_install();f.active=True;real=lifecycle.write_root
        def write(path,*args,**kwargs):
            if path==f.helper:self.assertTrue(f.active)
            return real(path,*args,**kwargs)
        with patch.object(lifecycle,'write_root',side_effect=write):f.install()
        self.assertTrue(f.active)

    def test_committed_primary_with_failed_mirror_reports_success_after_finalizing(self):
        f=self.fixture;real=lifecycle.write_root;failed=False
        def write(path,text,*args,**kwargs):
            nonlocal failed
            if path==f.transaction/'journal.mirror.json' and '"phase": "committed"' in text and not failed:
                failed=True;raise OSError('Injected mirror failure')
            return real(path,text,*args,**kwargs)
        with patch.object(lifecycle,'write_root',side_effect=write):f.install()
        self.assertTrue(f.helper.exists());self.assertTrue(f.record.exists());self.assertFalse(f.transaction.exists())

    def test_recovery_never_reenables_access_for_a_removed_plugin(self):
        f=self.fixture;f.seed_old_install();f.active=True;f.fail_menu='install';real=lifecycle.recover_installation;calls=0
        def interrupt():
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Interrupted rollback')
            return real()
        with patch.object(lifecycle,'recover_installation',side_effect=interrupt):
            with self.assertRaises(OSError):f.install()
        lifecycle.shutil.rmtree(f.plugin);real()
        self.assertFalse(f.rule.exists());self.assertFalse(f.helper.exists())
        self.assertFalse(f.enabled or f.active);self.assertFalse(f.transaction.exists())

    def test_interrupted_file_restore_keeps_live_record_and_code_intact(self):
        f=self.fixture;f.seed_old_install()
        lifecycle.directory(f.transaction,0o711)
        entries=lifecycle.snapshot_artifacts()
        (f.lib/'lifecycle.py').write_text('# current cleanup entry point\n')
        before=f.record.read_bytes();copy=lifecycle.shutil.copy2
        def interrupt(source,target,*args,**kwargs):
            if Path(source)==f.transaction/'backup/3':
                Path(target).write_text('');raise SystemExit('Power loss during copy')
            return copy(source,target,*args,**kwargs)
        with patch.object(lifecycle.shutil,'copy2',side_effect=interrupt):
            with self.assertRaises(SystemExit):lifecycle.restore_artifacts(entries)
        self.assertEqual(f.record.read_bytes(),before)
        # The old snapshot intentionally lacks lifecycle.py; removal of extras
        # follows successful replacement of every saved module.
        lifecycle.restore_artifacts(entries)
        self.assertEqual(f.record.read_bytes(),before)

    def test_cleanup_recovers_an_empty_record_using_the_journal(self):
        f=self.fixture;f.seed_old_install();real=lifecycle.recover_installation
        f.fail_menu='install'
        with patch.object(lifecycle,'recover_installation',side_effect=[None,SystemExit('Power loss')]):
            with self.assertRaises(SystemExit):f.install()
        f.record.write_text('')
        import shutil
        shutil.rmtree(f.plugin)
        lifecycle.dispatch(['check'])
        self.assertFalse(f.rule.exists());self.assertFalse(f.record.exists())

    def test_first_install_activates_watcher_before_granting_access(self):
        f=self.fixture;write=lifecycle.write_root
        def checked(path,*args,**kwargs):
            if path in [f.helper,f.rule]:
                self.assertTrue(f.enabled);self.assertTrue(f.active)
                self.assertTrue(f.record.exists())
            return write(path,*args,**kwargs)
        with patch.object(lifecycle,'write_root',side_effect=checked):f.install()

    def test_first_install_rollback_revokes_before_removing_cleanup_code(self):
        f=self.fixture;remove=lifecycle.shutil.rmtree
        def checked(path,*args,**kwargs):
            if Path(path)==f.lib:
                self.assertFalse(f.rule.exists());self.assertFalse(f.helper.exists())
            return remove(path,*args,**kwargs)
        f.fail_menu='install'
        with patch.object(lifecycle.shutil,'rmtree',side_effect=checked):
            with self.assertRaises(OSError):f.install()
