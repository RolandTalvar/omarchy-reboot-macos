from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from menu_state import install_menu,remove_menu,sync_strings,read_menu,paths,patch_rows,parse_menu

STRINGS={'menu.label':'Reboot into macOS','menu.description':'Boot once','menu.shutdown':'Shutdown'}

class MenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'omarchy'
        self.menu=self.root/'extensions/omarchy-menu.jsonc'
        self.menu.parent.mkdir(parents=True)
    def write(self,data): self.menu.write_text(json.dumps(data))
    def test_exact_comments_restored_when_unchanged(self):
        original='// My settings\n{\n "system.shutdown": {"label":"Power off", "action":"save-and-shutdown", "when":"test -f /tmp/ready"},\n "personal.notes":{"label":"Notes"},\n}\n'
        self.menu.write_text(original)
        install_menu(self.root,STRINGS)
        rows=read_menu(self.menu)
        self.assertEqual(rows['system.shutdown-last']['action'],'save-and-shutdown')
        self.assertEqual(rows['system.shutdown-last']['label'],'Power off')
        self.assertEqual(rows['system.shutdown-last']['when'],'test -f /tmp/ready')
        remove_menu(self.root)
        self.assertEqual(self.menu.read_text(),original)
    def test_unrelated_edits_survive_removal(self):
        self.write({'personal.notes':{'label':'Old'}})
        install_menu(self.root,STRINGS)
        data=read_menu(self.menu);data['personal.notes']['label']='New';self.write(data)
        remove_menu(self.root)
        self.assertEqual(read_menu(self.menu),{'personal.notes':{'label':'New'}})
    def test_manual_shutdown_edit_survives(self):
        self.write({'system.shutdown':{'action':'my-shutdown'}})
        install_menu(self.root,STRINGS)
        data=read_menu(self.menu);data['system.shutdown']['label']='New custom label';self.write(data)
        remove_menu(self.root)
        self.assertEqual(read_menu(self.menu)['system.shutdown'],{'action':'my-shutdown','label':'New custom label'})
    def test_manual_replacement_action_is_not_removed(self):
        self.write({});install_menu(self.root,STRINGS)
        data=read_menu(self.menu);data['system.reboot-macos']['action']='my-new-command';self.write(data)
        remove_menu(self.root)
        self.assertEqual(read_menu(self.menu)['system.reboot-macos']['action'],'my-new-command')
    def test_setup_is_idempotent(self):
        self.write({'system.shutdown':{'action':'original'}})
        install_menu(self.root,STRINGS);install_menu(self.root,STRINGS);remove_menu(self.root)
        self.assertEqual(read_menu(self.menu),{'system.shutdown':{'action':'original'}})
    def test_no_original_menu_file_is_restored_to_absence(self):
        install_menu(self.root,STRINGS);remove_menu(self.root)
        self.assertFalse(self.menu.exists())
    def test_custom_shutdown_label_is_not_translated(self):
        self.write({'system.shutdown':{'label':'My power action','action':'custom'}})
        install_menu(self.root,STRINGS)
        sync_strings(self.root,{**STRINGS,'menu.shutdown':'Translated'})
        self.assertEqual(read_menu(self.menu)['system.shutdown-last']['label'],'My power action')
    def test_foreign_row_conflict_is_not_overwritten(self):
        original={'system.reboot-macos':{'action':'custom'}}
        self.write(original)
        with self.assertRaises(ValueError):install_menu(self.root,STRINGS)
        self.assertEqual(read_menu(self.menu),original)
    def test_translated_menu_still_restores_original(self):
        original='{"personal.notes":{"label":"Notes"}}'
        self.menu.write_text(original);install_menu(self.root,STRINGS)
        sync_strings(self.root,{**STRINGS,'menu.label':'Taaskäivita macOS-i'})
        remove_menu(self.root)
        self.assertEqual(self.menu.read_text(),original)
    def test_wrapped_items_are_preserved(self):
        original={'version':1,'items':{'personal.notes':{'label':'Notes'}}}
        self.write(original);install_menu(self.root,STRINGS);remove_menu(self.root)
        self.assertEqual(read_menu(self.menu),original)

    def test_comment_added_while_installed_survives_removal(self):
        self.menu.write_text('{"personal.notes":{"label":"Notes"}}')
        install_menu(self.root,STRINGS)
        self.menu.write_text('// Added after setup\n'+self.menu.read_text())
        remove_menu(self.root)
        self.assertIn('// Added after setup',self.menu.read_text())
        self.assertEqual(read_menu(self.menu),{'personal.notes':{'label':'Notes'}})
    def test_unrelated_comment_survives_language_change(self):
        self.menu.write_text('// Keep this note\n{"personal.notes":{"label":"Notes"}}')
        install_menu(self.root,STRINGS)
        sync_strings(self.root,{**STRINGS,'menu.label':'Translated'})
        self.assertIn('// Keep this note',self.menu.read_text())

    def test_comment_only_and_blank_menus_accept_new_rows(self):
        for raw in ['','  \n','// notes\n','  // notes without newline']:
            with self.subTest(raw=raw):
                changed=patch_rows(raw,{'system.reboot-macos':{'label':'macOS'}})
                self.assertEqual(parse_menu(changed)['system.reboot-macos']['label'],'macOS')
    def test_comments_after_last_value_survive_addition_and_replacement(self):
        raw='{\n "personal.notes":{"label":"Notes"}\n // keep this comment\n}\n'
        for changes in [{'system.reboot-macos':{'label':'macOS'}},{'personal.notes':{'label':'Changed'}}]:
            with self.subTest(changes=changes):
                changed=patch_rows(raw,changes)
                self.assertIn('// keep this comment',changed)
                for key,value in changes.items():self.assertEqual(parse_menu(changed)[key],value)
