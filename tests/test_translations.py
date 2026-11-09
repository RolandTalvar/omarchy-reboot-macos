import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from translations import CATALOGS, selected_language, translate
from sync_menu import sync_menu

class TranslationTests(unittest.TestCase):
    def test_all_fifty_catalogs_have_same_keys_and_placeholders(self):
        english = json.loads((CATALOGS / 'en.json').read_text())
        paths = list(CATALOGS.glob('*.json'))
        self.assertEqual(len(paths), 50)
        for path in paths:
            with self.subTest(language=path.stem):
                catalog = json.loads(path.read_text())
                self.assertEqual(set(catalog), set(english))
                for key, text in catalog.items():
                    self.assertIsInstance(text, str)
                    self.assertTrue(text.strip())
                    self.assertEqual(re.findall(r'%\d+', text), re.findall(r'%\d+', english[key]))
    def test_selected_language_is_read_live(self):
        with tempfile.TemporaryDirectory() as directory:
            language = Path(directory) / 'language'
            with patch.dict(os.environ, {'OMARCHY_LANGUAGE_FILE': str(language)}):
                self.assertEqual(selected_language(), 'en')
                language.write_text('et\n')
                self.assertEqual(translate('yes'), 'Jah')
                language.write_text('fr\n')
                self.assertEqual(translate('yes'), 'Oui')
                language.write_text('../../etc/passwd')
                self.assertEqual(selected_language(), 'en')
    def test_regional_base_and_english_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / 'en.json').write_text('{"first":"English", "second":"Fallback"}')
            (directory / 'pt.json').write_text('{"first":"Português"}')
            self.assertEqual(translate('first', language='pt-BR', directory=directory), 'Português')
            self.assertEqual(translate('second', language='pt-BR', directory=directory), 'Fallback')
            self.assertEqual(translate('second', language='xx', directory=directory), 'Fallback')
            self.assertEqual(translate('unknown', language='xx', directory=directory), 'unknown')
    def test_volume_name_is_preserved_without_recursive_substitution(self):
        name = 'My %1 macOS 日本語'
        self.assertIn(name, translate('confirm', name, language='et'))
    def test_corrupt_catalog_uses_english(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / 'en.json').write_text('{"yes":"Yes"}')
            (directory / 'et.json').write_text('broken')
            self.assertEqual(translate('yes', language='et', directory=directory), 'Yes')
    def test_menu_sync_changes_only_owned_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'menu.jsonc'
            data = {'personal.notes': {'label':'Notes'}, 'system.reboot-macos': {'action':'omarchy-shell rolandtlvr.reboot-macos reboot'}, 'system.shutdown-last': {'action':'omarchy-system shutdown'}}
            path.write_text(json.dumps(data))
            strings = {key: translate(key, language='et') for key in ['menu.label','menu.description','menu.shutdown']}
            self.assertTrue(sync_menu(path, strings))
            result = json.loads(path.read_text())
            self.assertEqual(result['personal.notes'], data['personal.notes'])
            self.assertEqual(result['system.reboot-macos']['label'], 'Taaskäivita macOS-i')
            self.assertEqual(result['system.shutdown-last']['label'], 'Lülita välja')
            self.assertFalse(sync_menu(path, strings))
    def test_sync_does_not_recreate_removed_or_replaced_menu_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'menu.jsonc'
            for data in [{}, {'system.reboot-macos':{'action':'my-custom-action'}}]:
                path.write_text(json.dumps(data))
                self.assertFalse(sync_menu(path, {}))
                self.assertEqual(json.loads(path.read_text()), data)
    def test_confirm_buttons_are_translated(self):
        import subprocess
        import reboot_macos
        volumes = json.dumps([{'index':1, 'name':'macOS Sequoia'}])
        with tempfile.TemporaryDirectory() as directory:
            language = Path(directory) / 'language'
            language.write_text('et')
            with patch.dict(os.environ, {'OMARCHY_LANGUAGE_FILE':str(language)}), patch.object(reboot_macos.subprocess, 'run', side_effect=[subprocess.CompletedProcess([],0,volumes),subprocess.CompletedProcess([],1)]) as run:
                self.assertEqual(reboot_macos.main(),130)
                args = run.call_args.args[0]
                self.assertIn('Jah',args)
                self.assertIn('Ei',args)
                self.assertIn('macOS Sequoia',args[-1])
                self.assertNotIn('Save your work',args[-1])
