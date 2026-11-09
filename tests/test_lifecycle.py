import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import lifecycle

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        lock = patch.object(lifecycle, 'LOCK', Path(temporary.name)/'setup.lock')
        lock.start(); self.addCleanup(lock.stop)

    def test_removed_directory_triggers_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/'record.json'
            saved={'account':'user','plugin':str(Path(directory)/'missing')}
            record.write_text(json.dumps(saved))
            with patch.object(lifecycle,'RECORD',record),patch.object(lifecycle.os,'geteuid',return_value=0),patch.object(lifecycle,'remove') as remove:
                lifecycle.main(['check']);remove.assert_called_once_with(saved)
    def test_existing_plugin_is_not_removed_during_update(self):
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/'record.json';plugin=Path(directory)/'plugin';plugin.mkdir()
            # Even a temporarily absent manifest must not trigger cleanup.
            record.write_text(json.dumps({'account':'user','plugin':str(plugin)}))
            with patch.object(lifecycle,'RECORD',record),patch.object(lifecycle.os,'geteuid',return_value=0),patch.object(lifecycle,'remove') as remove:
                lifecycle.main(['check']);remove.assert_not_called()
    def test_cleanup_drops_privileges_before_touching_user_menu(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);lib=root/'lib';lib.mkdir();(lib/'menu_state.py').touch()
            units=root/'units';units.mkdir()
            with patch.multiple(lifecycle,LIB=lib,HELPER=root/'helper',RULE=root/'sudoers',RECORD=root/'record',UNITS=units),patch.object(lifecycle,'run') as run:
                lifecycle.remove({'account':'user','config':'/home/user/.config'})
                first=run.call_args_list[0].args
                self.assertEqual(first[:6],('/usr/bin/runuser','-u','user','--','/usr/bin/python3','-I'))
                self.assertFalse(lib.exists())
    def test_failed_user_restore_leaves_helper_for_recovery(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'menu_state.py').touch()
            with patch.multiple(lifecycle,LIB=root,HELPER=root/'helper',RULE=root/'rule',RECORD=root/'record',UNITS=root/'units'),patch.object(lifecycle,'run',side_effect=subprocess.CalledProcessError(1,'restore')):
                with self.assertRaises(subprocess.CalledProcessError):lifecycle.remove({'account':'user','config':'/home/user/.config'})
                self.assertTrue((root/'menu_state.py').exists())
