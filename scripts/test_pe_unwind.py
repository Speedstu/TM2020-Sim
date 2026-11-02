import struct
import unittest
from pe_unwind import RuntimeRange, UnwindIndex


class ChainedUnwindTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(256)
        data[32:36] = bytes([1, 0, 0, 0])
        data[64:68] = bytes([0x21, 0, 3, 0])  # odd slot count: pad to 4
        data[76:88] = struct.pack('<III', 1000, 1010, 32)
        data[96:100] = bytes([0x21, 0, 0, 0])
        data[100:112] = struct.pack('<III', 2000, 2010, 64)
        ranges = [RuntimeRange(1000, 1010, 32), RuntimeRange(2000, 2010, 64), RuntimeRange(3000, 3010, 96)]
        return data, ranges

    def test_noncontiguous_multiple_chains(self):
        data, ranges = self.fixture(); index = UnwindIndex(ranges, lambda a,n: data[a:a+n])
        self.assertEqual(index.root(3005), 1000)
        self.assertEqual(len(index.groups[1000]), 3)
        self.assertIsNone(index.root(1500)); self.assertIsNone(index.root(3010))

    def test_rejects_missing_or_mismatched_parent(self):
        data, ranges = self.fixture(); data[76:88] = struct.pack('<III', 1000, 1011, 32)
        with self.assertRaises(ValueError): UnwindIndex(ranges, lambda a,n: data[a:a+n])

    def test_rejects_cycle(self):
        data, ranges = self.fixture(); data[32:36] = bytes([0x21, 0, 0, 0])
        data[36:48] = struct.pack('<III', 3000, 3010, 96)
        with self.assertRaises(ValueError): UnwindIndex(ranges, lambda a,n: data[a:a+n])

    def test_rejects_chain_and_handler_flags(self):
        data, ranges = self.fixture(); data[64] = 0x29
        with self.assertRaises(ValueError): UnwindIndex(ranges, lambda a,n: data[a:a+n])

    def test_rejects_short_header(self):
        _, ranges = self.fixture()
        with self.assertRaises(ValueError): UnwindIndex(ranges, lambda a,n: b'')


if __name__ == '__main__': unittest.main()
