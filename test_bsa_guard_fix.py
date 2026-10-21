import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bsa_guard_fix as fix


@unittest.skipUnless(os.name == 'nt', 'Windows installer')
class AdapterInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'lab'
        folder = self.root / fix.FOLDER
        folder.mkdir(parents=True)
        (self.root / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(Path(self.temp.name) / 'source')}))
        self.target = folder / 'BSAMemoryMap.dll'
        self.backup = folder / 'BSAMemoryMap.native.bin'
        self.original = b'installed native bytes'
        self.replacement = b'tested adapter bytes'
        self.target.write_bytes(self.original)
        self.adapter = self.root / 'tested.dll'
        self.adapter.write_bytes(self.replacement)
        for mocker in (patch.object(fix, 'NATIVE_HASH', fix.digest(self.original)),
                       patch.object(fix, 'ADAPTER_HASH', fix.digest(self.replacement)),
                       patch.object(fix.subprocess, 'check_output', return_value='')):
            mocker.start()
            self.addCleanup(mocker.stop)

    def test_install_restore_and_idempotence(self):
        fix.apply(self.root, self.adapter)
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(self.target.read_bytes(), self.replacement)
        self.assertEqual(fix.apply(self.root, self.adapter)['status'], 'already installed')
        fix.apply(self.root, restore=True)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_unknown_adapter_never_changes_native(self):
        self.adapter.write_bytes(b'unknown')
        with self.assertRaises(ValueError):
            fix.apply(self.root, self.adapter)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())

    def test_corrupt_backup_refuses_restore(self):
        fix.apply(self.root, self.adapter)
        self.backup.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            fix.apply(self.root, restore=True)
        self.assertEqual(self.target.read_bytes(), self.replacement)

    def test_user_change_is_not_overwritten(self):
        fix.apply(self.root, self.adapter)
        self.target.write_bytes(b'user change')
        with self.assertRaises(ValueError):
            fix.apply(self.root, restore=True)
        self.assertEqual(self.target.read_bytes(), b'user change')

    def test_running_client_refused(self):
        with patch.object(fix.subprocess, 'check_output', return_value='"SkyrimTogether.exe","42"'):
            with self.assertRaises(ValueError):
                fix.apply(self.root, self.adapter)
        self.assertFalse(self.backup.exists())

    def test_original_installation_refused(self):
        (self.root / 'LORERIM_LAB.json').write_text(json.dumps({'source': str(self.root)}))
        with self.assertRaises(ValueError):
            fix.apply(self.root, self.adapter)

    def test_shared_native_refused(self):
        os.link(self.target, self.root / 'shared.dll')
        with self.assertRaises(ValueError):
            fix.apply(self.root, self.adapter)
        self.assertFalse(self.backup.exists())
