import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import dosemetha_fix as fix


@unittest.skipUnless(os.name == 'nt', 'Windows installer')
class LoadOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'lab'
        self.folder = self.root / fix.DIRECTORY
        self.folder.mkdir(parents=True)
        (self.root / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(Path(self.temp.name) / 'source')}))
        self.data = b'unchanged test dll'
        self.old, self.new = self.folder / fix.ORIGINAL, self.folder / fix.EARLY
        self.old.write_bytes(self.data)
        for mocker in (patch.object(fix, 'SHA256', hashlib.sha256(self.data).hexdigest()),
                       patch.object(fix.subprocess, 'check_output', return_value='')):
            mocker.start()
            self.addCleanup(mocker.stop)

    def test_install_idempotence_and_restore_preserve_bytes(self):
        fix.apply(self.root)
        self.assertFalse(self.old.exists())
        self.assertEqual(self.new.read_bytes(), self.data)
        self.assertEqual(fix.apply(self.root)['status'], 'already installed')
        fix.apply(self.root, restore=True)
        self.assertEqual(self.old.read_bytes(), self.data)
        self.assertFalse(self.new.exists())
        self.assertEqual(fix.apply(self.root, restore=True)['status'], 'already restored')

    def test_duplicate_is_not_overwritten(self):
        self.new.write_bytes(b'other')
        with self.assertRaises(ValueError):
            fix.apply(self.root)
        self.assertEqual(self.old.read_bytes(), self.data)
        self.assertEqual(self.new.read_bytes(), b'other')

    def test_unknown_dll_refused(self):
        self.old.write_bytes(b'other')
        with self.assertRaises(ValueError):
            fix.apply(self.root)
        self.assertFalse(self.new.exists())

    def test_game_running_refused(self):
        with patch.object(fix.subprocess, 'check_output', return_value='"SkyrimTogether.exe","42"'):
            with self.assertRaises(ValueError):
                fix.apply(self.root)
        self.assertTrue(self.old.exists())

    def test_original_installation_refused(self):
        (self.root / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(self.root)}))
        with self.assertRaises(ValueError):
            fix.apply(self.root)

    def test_shared_file_refused(self):
        os.link(self.old, self.root / 'shared.dll')
        with self.assertRaises(ValueError):
            fix.apply(self.root)
        self.assertTrue(self.old.exists())
