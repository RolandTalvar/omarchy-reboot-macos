import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

helper = module('boot_helper')
ui = module('reboot_macos')

class BootTests(unittest.TestCase):
    def test_parse_current_and_custom_names(self):
        self.assertEqual(helper.parse_volumes(' 1) macOS Sequoia\n*2) Omarchy\n')[0], {'index': 1, 'name': 'macOS Sequoia', 'current': False})
    def test_bad_and_duplicate_output(self):
        for text in ['', 'error', ' 1) a\n 1) b']:
            with self.assertRaises(ValueError): helper.parse_volumes(text)
    def test_unique_macos_names(self):
        for name in ['macOS Sequoia', 'Macintosh HD', 'Mac OS X']:
            v = [{'index': 1, 'name': name}, {'index': 2, 'name': 'Omarchy'}]
            self.assertEqual(ui.detect_macos(v), v[0])
    def test_ambiguous_or_renamed_requires_choice(self):
        for names in [['Work', 'Omarchy'], ['macOS Work', 'macOS Personal']]:
            self.assertIsNone(ui.detect_macos([{'name': n} for n in names]))
    def test_invalid_arguments_never_execute(self):
        for args in [[], ['--select-next', '-1'], ['--select-next', '1; reboot'], ['--set-boot-macos']]:
            with patch.object(helper.subprocess, 'run') as run:
                with self.assertRaises(ValueError): helper.main(args)
                run.assert_not_called()
    def test_missing_volume_never_sets_boot(self):
        with patch.object(helper, 'list_volumes', return_value=[{'index': 2}]), patch.object(helper.subprocess, 'run') as run:
            with self.assertRaises(ValueError): helper.main(['--select-next', '1'])
            run.assert_not_called()
    def test_selection_is_next_boot_only(self):
        with patch.object(helper, 'list_volumes', return_value=[{'index': 1}]), patch.object(helper.subprocess, 'run') as run:
            helper.main(['--select-next', '1'])
            self.assertEqual(run.call_args.args[0], [helper.BLESS, '--next', '--set-boot', '1', '--yes'])
    def test_cancel_does_not_select_or_reboot(self):
        import json
        volumes = [{'index': 1, 'name': 'macOS Sequoia', 'current': False}]
        with patch.object(ui.subprocess, 'run', side_effect=[subprocess.CompletedProcess([],0,json.dumps(volumes)), subprocess.CompletedProcess([],1)]) as run:
            self.assertEqual(ui.main(), 130)
            self.assertEqual(run.call_count, 2)
    def test_selection_failure_prevents_reboot(self):
        import json
        v = json.dumps([{'index': 1, 'name': 'macOS Sequoia'}])
        replies = [subprocess.CompletedProcess([],0,v), subprocess.CompletedProcess([],0), subprocess.CompletedProcess([],0,v), subprocess.CalledProcessError(1, 'select')]
        with patch.object(ui.subprocess, 'run', side_effect=replies) as run:
            with self.assertRaises(subprocess.CalledProcessError): ui.main()
            self.assertFalse(any(c.args[0][:2] == ['omarchy', 'system'] for c in run.call_args_list))

if __name__ == '__main__': unittest.main()
