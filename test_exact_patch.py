import unittest
from camera_fix import digest, patch_bytes


class ExactInstructionPatchTests(unittest.TestCase):
    def test_call_removal_preserves_surrounding_instructions(self):
        before = bytes.fromhex('4533c0ba40000000488bc8e8513a0200488d4df7')
        call = bytes.fromhex('e8513a0200')
        after = patch_bytes(before, digest(before), ((11, call, b'\x90' * 5),))
        self.assertEqual(after[:11], before[:11])
        self.assertEqual(after[11:16], b'\x90' * 5)
        self.assertEqual(after[16:], before[16:])
        self.assertEqual(len(after), len(before))

    def test_hash_and_instruction_context_are_both_required(self):
        data = b'header' + bytes.fromhex('e8513a0200') + b'trailer'
        with self.assertRaises(ValueError):
            patch_bytes(data, 'unknown', ((6, data[6:11], b'\x90' * 5),))
        with self.assertRaises(ValueError):
            patch_bytes(data, digest(data), ((6, b'wrong', b'\x90' * 5),))

    def test_extent_change_is_refused(self):
        data = bytes.fromhex('e8513a0200')
        with self.assertRaises(ValueError):
            patch_bytes(data, digest(data), ((0, data, b'\x90'),))
