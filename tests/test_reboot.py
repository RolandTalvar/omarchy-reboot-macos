import json
import subprocess
import unittest
from unittest.mock import patch
import boot_helper as helper
import reboot_macos as ui

ID='a'*64
VOLUME={'index':1,'name':'Renamed system','current':False,'os':'macos','id':ID,'selectable':True}

def reply(value=None,code=0):
    return subprocess.CompletedProcess([],code,json.dumps(value) if value is not None else '')

class BootTests(unittest.TestCase):
    def test_parse_current_and_custom_names(self):
        self.assertEqual(helper.parse_volumes(' 1) macOS Sequoia\n*2) Omarchy\n')[0], {'index':1,'name':'macOS Sequoia','current':False})
    def test_bad_and_duplicate_output(self):
        for text in ['', 'error', ' 1) a\n 1) b']:
            with self.assertRaises(ValueError): helper.parse_volumes(text)
    def test_auto_detection_ignores_names(self):
        self.assertEqual(ui.detect_macos([VOLUME, {'name':'macOS FAKE','os':'unknown','selectable':True}]),VOLUME)
        self.assertIsNone(ui.detect_macos([{'name':'macOS Fake','os':'unknown','selectable':True}]))
    def test_multiple_macos_candidates_require_choice(self):
        self.assertIsNone(ui.detect_macos([VOLUME,{**VOLUME,'id':'b'*64}]))
    def test_unselectable_volume_not_auto_selected(self):
        self.assertIsNone(ui.detect_macos([{**VOLUME,'selectable':False}]))
    def test_invalid_arguments_never_execute(self):
        for args in [[],['--select-next','-1'],['--select-next','1; reboot'],['--set-boot-macos']]:
            with patch.object(helper.subprocess,'run') as run:
                with self.assertRaises(ValueError): helper.main(args)
                run.assert_not_called()
    def test_missing_identity_never_sets_boot(self):
        with patch.object(helper,'list_volumes',return_value=[]),patch.object(helper.subprocess,'run') as run:
            with self.assertRaises(ValueError): helper.main(['--select-next',ID])
            run.assert_not_called()
    def test_selection_uses_unique_name_not_unstable_index(self):
        with patch.object(helper,'list_volumes',return_value=[VOLUME]),patch.object(helper.subprocess,'run') as run:
            helper.main(['--select-next',ID])
            self.assertEqual(run.call_args.args[0],[helper.BLESS,'--next','--set-boot','Renamed system','--yes'])
    def test_duplicate_name_cannot_select(self):
        with patch.object(helper,'list_volumes',return_value=[{**VOLUME,'selectable':False}]),patch.object(helper.subprocess,'run') as run:
            with self.assertRaises(ValueError): helper.main(['--select-next',ID])
            run.assert_not_called()
    def test_metadata_maps_sealed_volume_independent_of_label(self):
        metadata=[{'name':'Custom','partition':'nvme0n1p2','vg_uuid':'abc','sealed_system':True}]
        with patch.object(helper,'system_metadata',return_value=metadata),patch.object(helper.subprocess,'run',return_value=subprocess.CompletedProcess([],0,' 1) Custom\n*2) macOS Fake\n')):
            volumes=helper.list_volumes()
            self.assertEqual(volumes[0]['os'],'macos')
            self.assertEqual(volumes[1]['os'],'unknown')
    def test_cancel_does_not_select_or_reboot(self):
        with patch.object(ui.subprocess,'run',side_effect=[reply([VOLUME]),reply(code=1)]) as run:
            self.assertEqual(ui.main(),130)
            self.assertEqual(run.call_count,2)
    def test_selection_failure_prevents_reboot(self):
        with patch.object(ui.subprocess,'run',side_effect=[reply([VOLUME]),reply(),reply([VOLUME]),subprocess.CalledProcessError(1,'select')]) as run:
            with self.assertRaises(subprocess.CalledProcessError): ui.main()
            self.assertFalse(any(c.args[0][0]=='systemd-run' for c in run.call_args_list))
    def test_reordered_or_changed_list_aborts(self):
        with patch.object(ui.subprocess,'run',side_effect=[reply([VOLUME]),reply(),reply([{**VOLUME,'index':2}])]):
            with self.assertRaises(ValueError): ui.main()
    def test_queue_failure_rolls_back_next_boot(self):
        with patch.object(ui.subprocess,'run',side_effect=[reply([VOLUME]),reply(),reply([VOLUME]),reply(),subprocess.CalledProcessError(1,'queue')]),patch.object(ui,'recover_selection') as recover:
            with self.assertRaises(subprocess.CalledProcessError): ui.main()
            recover.assert_called_once()
    def test_worker_failure_rolls_back_and_notifies(self):
        with patch.object(ui.subprocess,'run',side_effect=[subprocess.CalledProcessError(1,'reboot'),reply(),reply()]) as run:
            self.assertEqual(ui.reboot_worker(ID),1)
            self.assertIn('--execute',run.call_args_list[0].args[0])
            self.assertEqual(run.call_args_list[1].args[0],['sudo','-n',ui.HELPER,'--clear-next',ID])
            self.assertEqual(run.call_args_list[2].args[0][0],'omarchy-notification-send')
    def test_failed_rollback_warns_selection_is_still_pending(self):
        with patch.object(ui.subprocess,'run',side_effect=[subprocess.CalledProcessError(1,'clear'),reply()]) as run:
            ui.recover_selection(ID)
            self.assertIn('next',run.call_args.args[0][-1].lower())
    def test_rollback_does_not_clear_a_different_next_target(self):
        with patch.object(helper,'list_volumes',return_value=[VOLUME]),patch.object(helper.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'Another OS\n')) as run:
            with self.assertRaises(ValueError):helper.main(['--clear-next',ID])
            self.assertEqual(run.call_count,1)
            self.assertNotIn('--clear-next',run.call_args.args[0])
    def test_rollback_clears_only_the_confirmed_target(self):
        with patch.object(helper,'list_volumes',return_value=[VOLUME]),patch.object(helper.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,'Renamed system\n'),reply()]) as run:
            helper.main(['--clear-next',ID])
            self.assertEqual(run.call_args.args[0],[helper.BLESS,'--clear-next'])
