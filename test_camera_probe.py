import unittest
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from camera_probe import main, probe, readable, scan_range


class ProbeTests(unittest.TestCase):
    def test_chunk_boundaries_and_overlapping_matches(self):
        data = b'xxxxabababxxxxabab'
        for chunk in range(4, len(data) + 2):
            reads = []
            def read(address, size):
                reads.append((address, size))
                return data[address - 100:address - 100 + size]
            self.assertEqual(scan_range(read, 100, 100 + len(data), b'abab', chunk), [104, 106, 114])
            self.assertTrue(all(100 <= a < a + n <= 100 + len(data) for a, n in reads))

    def test_single_byte_and_empty_range(self):
        self.assertEqual(scan_range(lambda a, n: b'a' * n, 0, 3, b'a', 1), [0, 1, 2])
        self.assertEqual(scan_range(lambda a, n: self.fail('read empty range'), 9, 9, b'a'), [])

    def test_incomplete_read_is_not_no_match(self):
        with self.assertRaises(OSError):
            scan_range(lambda a, n: b'', 0, 100, b'ab')
        def fail(a, n):
            raise OSError('access denied')
        with self.assertRaises(OSError):
            scan_range(fail, 0, 100, b'ab')

    def test_invalid_arguments(self):
        for start, end, pattern, chunk in [(0, 1, b'', 1), (2, 1, b'a', 1), (0, 9, b'ab', 1)]:
            with self.assertRaises(ValueError):
                scan_range(lambda a, n: b'', start, end, pattern, chunk)

    def test_protections(self):
        for protect in (2, 4, 8, 0x20, 0x40, 0x80):
            self.assertTrue(readable(0x1000, protect))
            self.assertFalse(readable(0x1000, protect | 0x100))
            self.assertFalse(readable(0x2000, protect))
        for protect in (0, 1, 0x10):
            self.assertFalse(readable(0x1000, protect))

    def test_cli_failure_is_saved_and_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'failure.json'
            with patch.object(sys, 'argv', ['camera_probe.py', '123', str(output)]), \
                    patch('camera_probe.probe', side_effect=OSError('denied')):
                self.assertEqual(main(), 3)
            self.assertFalse(json.loads(output.read_text())['readable_regions_complete'])

    def test_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'capture.json'
            output.write_text('prior evidence')
            with patch.object(sys, 'argv', ['camera_probe.py', '123', str(output)]), \
                    patch('camera_probe.probe') as capture:
                with self.assertRaises(FileExistsError):
                    main()
                capture.assert_not_called()
            self.assertEqual(output.read_text(), 'prior evidence')

    @unittest.skipUnless(os.name == 'nt' and ctypes.sizeof(ctypes.c_void_p) == 8, 'Windows x64 integration')
    def test_windows_read_only_self_probe(self):
        result = probe(os.getpid(), Path(sys.executable).name)
        self.assertGreater(result['image']['size'], 0)
        self.assertTrue(result['readable_regions_complete'])
        self.assertTrue(any(r['read'] for r in result['regions']))
        self.assertEqual(result['errors'], [])


if __name__ == '__main__':
    unittest.main()
