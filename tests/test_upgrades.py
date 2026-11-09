from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
import lifecycle
from menu_state import install_menu, paths, read_menu, remove_menu, sync_strings
from install_fixture import InstallationFixture, SOURCE

STRINGS={'menu.label':'Reboot into macOS','menu.description':'Boot once','menu.shutdown':'Shutdown'}

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=InstallationFixture();self.addCleanup(self.fixture.close)
    def release(self,name):
        directory=self.fixture.root/name;directory.mkdir()
        for path in SOURCE.glob('*.py'):shutil.copy2(path,directory/path.name)
        shutil.copytree(SOURCE/'i18n',directory/'i18n')
        helper=directory/'boot_helper.py'
        helper.write_text(helper.read_text()+'\n# Release '+name+'\n')
        return directory
    def test_successful_upgrade_replaces_helper_but_retains_original_menu_backup(self):
        f=self.fixture;old=self.release('old');new=self.release('new')
        f.install(old)
        state_path=paths(f.config/'omarchy')[1]
        original_state=state_path.read_bytes()
        previous_helper=f.helper.read_bytes()
        f.install(new)
        self.assertNotEqual(f.helper.read_bytes(),previous_helper)
        self.assertEqual(f.helper.read_bytes(),(new/'boot_helper.py').read_bytes())
        self.assertEqual(f.helper.stat().st_mode & 0o777,0o755)
        self.assertEqual(f.rule.stat().st_mode & 0o777,0o440)
        self.assertEqual(state_path.read_bytes(),original_state)
        for name in ['apfs_metadata.py','menu_state.py','lifecycle.py','menu_install.py','translations.py']:
            self.assertEqual((f.lib/name).read_bytes(),(new/name).read_bytes())
        self.assertTrue(f.active and f.enabled)
        self.assertFalse(f.transaction.exists())
        remove_menu(f.config/'omarchy')
        self.assertEqual(f.menu.read_bytes(),f.initial_menu)
    def test_translations_and_user_changes_survive_upgrade_and_removal(self):
        f=self.fixture;f.install(self.release('old'))
        original=deepcopy(json.loads(paths(f.config/'omarchy')[1].read_text())['before'])
        sync_strings(f.config/'omarchy',{**STRINGS,'menu.label':'Taaskäivita macOS-i'})
        data=read_menu(f.menu)
        data['personal.notes']={'label':'My new notes','action':'notes'}
        data['system.reboot-macos']['label']='My macOS shortcut'
        data['system.shutdown']['label']='My updated power label'
        f.menu.write_text('// Added after installation\n'+json.dumps(data))
        f.install(self.release('new'))
        current=read_menu(f.menu)
        self.assertEqual(current['system.reboot-macos']['label'],'My macOS shortcut')
        self.assertEqual(current['system.shutdown-last']['action'],'my-save-and-shutdown')
        state=json.loads(paths(f.config/'omarchy')[1].read_text())
        self.assertEqual(state['before'],original)
        remove_menu(f.config/'omarchy')
        current=read_menu(f.menu)
        self.assertEqual(current['personal.notes']['action'],'notes')
        self.assertEqual(current['system.shutdown']['action'],'my-save-and-shutdown')
        self.assertEqual(current['system.shutdown']['label'],'My updated power label')
        self.assertIn('// Added after installation',f.menu.read_text())
    def test_old_legacy_menu_state_migrates_without_losing_custom_shutdown(self):
        f=self.fixture
        before=read_menu(f.menu)
        backup={key:before.get(key) for key in ['system.reboot-macos','system.shutdown','system.shutdown-last']}
        root=f.config/'omarchy'
        (root/'reboot-macos-menu-backup.json').write_text(json.dumps(backup))
        f.menu.write_text(json.dumps({
            'system.reboot-macos':{'action':'omarchy-shell rolandtlvr.reboot-macos reboot'},
            'system.shutdown':{'when':'false'},
            'system.shutdown-last':{'label':'Shutdown','action':'omarchy-system shutdown'}}))
        f.seed_old_install()
        f.install(self.release('new'))
        current=read_menu(f.menu)
        self.assertEqual(current['system.shutdown-last']['action'],'my-save-and-shutdown')
        self.assertFalse((root/'reboot-macos-menu-backup.json').exists())
        remove_menu(root)
        self.assertEqual(read_menu(f.menu),before)
    def test_source_update_cannot_replace_installed_privileged_code_without_setup(self):
        f=self.fixture;release=self.release('first');f.install(release)
        helper=f.helper.read_bytes();module=(f.lib/'apfs_metadata.py').read_bytes()
        with (release/'boot_helper.py').open('a') as output:output.write('# changed checkout\n')
        with (release/'apfs_metadata.py').open('a') as output:output.write('# changed metadata reader\n')
        self.assertEqual(f.helper.read_bytes(),helper)
        self.assertEqual((f.lib/'apfs_metadata.py').read_bytes(),module)
        f.install(release)
        self.assertNotEqual(f.helper.read_bytes(),helper)
        self.assertNotEqual((f.lib/'apfs_metadata.py').read_bytes(),module)
    def test_failed_upgrade_can_retry_without_changing_original_removal_state(self):
        f=self.fixture;f.install(self.release('old'))
        before=f.files();state=paths(f.config/'omarchy')[1].read_bytes();menu=f.menu.read_bytes()
        f.fail_menu='install'
        with self.assertRaises(OSError):f.install(self.release('failed'))
        self.assertEqual(f.files(),before)
        self.assertEqual(paths(f.config/'omarchy')[1].read_bytes(),state)
        self.assertEqual(f.menu.read_bytes(),menu)
        f.install(self.release('retry'))
        self.assertEqual(paths(f.config/'omarchy')[1].read_bytes(),state)
        remove_menu(f.config/'omarchy')
        self.assertEqual(f.menu.read_bytes(),f.initial_menu)

    def test_upgrade_removes_obsolete_trusted_modules(self):
        f=self.fixture;f.install(self.release('old'))
        obsolete=f.lib/'retired-module.py';obsolete.write_text('# no longer part of the helper\n')
        f.install(self.release('new'))
        self.assertFalse(obsolete.exists())
