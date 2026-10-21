import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import camera_fix as fix


@unittest.skipUnless(os.name == 'nt', 'Windows installer')
class CameraFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lab = Path(self.temp.name) / 'lab'
        self.lab.mkdir()
        (self.lab / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(Path(self.temp.name) / 'original')}))
        self.target = self.lab / fix.DLL
        self.target.parent.mkdir(parents=True)
        self.original = b'header' + bytes.fromhex('a82074660fbae0087260') + b'trailer'
        self.target.write_bytes(self.original)
        for mocker in (patch.object(fix, 'ORIGINAL_SHA256', fix.digest(self.original)),
                       patch.object(fix, 'PATCHES', ((6, self.original[6:16]),)),
                       patch.object(fix.subprocess, 'check_output', return_value='')):
            mocker.start()
            self.addCleanup(mocker.stop)

    def test_exact_change_idempotence_and_rollback(self):
        fix.apply(self.lab)
        changed = self.target.read_bytes()
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.original, changed)) if a != b], [7])
        self.assertEqual(changed[7], 0x60)
        self.assertEqual(fix.apply(self.lab)['status'], 'already patched')
        fix.apply(self.lab, restore=True)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_unknown_binary_refused_without_backup(self):
        self.target.write_bytes(b'unknown')
        with self.assertRaises(ValueError):
            fix.apply(self.lab)
        self.assertFalse((self.lab / 'camera-fix-backup').exists())
        self.assertEqual(self.target.read_bytes(), b'unknown')

    def test_changed_file_after_patch_refused(self):
        fix.apply(self.lab)
        self.target.write_bytes(b'user change')
        with self.assertRaises(ValueError):
            fix.apply(self.lab, restore=True)
        self.assertEqual(self.target.read_bytes(), b'user change')

    def test_running_game_refused(self):
        with patch.object(fix.subprocess, 'check_output', return_value='"SkyrimTogether.exe","123"'):
            with self.assertRaises(ValueError):
                fix.apply(self.lab)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_original_tree_refused(self):
        (self.lab / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(self.lab)}))
        with self.assertRaises(ValueError):
            fix.apply(self.lab)

    def test_hardlinked_dll_refused(self):
        os.link(self.target, self.lab / 'shared.dll')
        with self.assertRaises(ValueError):
            fix.apply(self.lab)
        self.assertEqual(self.target.read_bytes(), self.original)
