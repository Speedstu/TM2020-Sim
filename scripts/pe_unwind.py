"""Read PE x64 chained unwind ranges without treating funclets as full functions.

Specification: https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64
Only version 1/2 records and valid .pdata chain targets are accepted.
"""
import bisect
from dataclasses import dataclass
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


@dataclass(frozen=True)
class RuntimeRange:
    begin: int
    end: int
    unwind: int


def chain_parent(record, read):
    header = read(record.unwind, 4)
    if len(header) != 4 or header[0] & 7 not in (1, 2):
        raise ValueError('Unsupported/truncated x64 unwind header')
    flags = header[0] >> 3
    if flags & ~7 or (flags & 4 and flags & 3):
        raise ValueError('Invalid x64 unwind flag combination')
    if not flags & 4:
        return None
    offset = 4 + ((header[2] + 1) & ~1) * 2
    data = read(record.unwind + offset, 12)
    if len(data) != 12:
        raise ValueError('Truncated chained RUNTIME_FUNCTION')
    return RuntimeRange(*struct.unpack('<III', data))


class UnwindIndex:
    def __init__(self, ranges, read):
        self.ranges = sorted(ranges, key=lambda r: r.begin)
        self.by_start = {r.begin: r for r in self.ranges}
        self.starts = [r.begin for r in self.ranges]
        if len(self.by_start) != len(self.ranges) or any(r.begin >= r.end for r in self.ranges):
            raise ValueError('Invalid/duplicate runtime ranges')
        if any(a.end > b.begin for a, b in zip(self.ranges, self.ranges[1:])):
            raise ValueError('Overlapping runtime ranges')
        self.parents = {}
        for r in self.ranges:
            parent = chain_parent(r, read)
            if parent is not None:
                if self.by_start.get(parent.begin) != parent:
                    raise ValueError('Unwind chain does not identify an exact .pdata entry')
                self.parents[r.begin] = parent.begin
        self.roots = {}; self.groups = {}
        for r in self.ranges:
            current = r.begin; seen = set()
            while current in self.parents:
                if current in seen:
                    raise ValueError('Cyclic unwind chain')
                seen.add(current); current = self.parents[current]
            self.roots[r.begin] = current
            self.groups.setdefault(current, []).append(r)

    def containing(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        return self.ranges[i] if i >= 0 and rva < self.ranges[i].end else None

    def root(self, rva):
        record = self.containing(rva)
        return self.roots[record.begin] if record else None


class PeCode:
    def __init__(self, path):
        self.pe = pefile.PE(str(path), fast_load=True)
        self.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
        # This analysis is scoped to the ordinary .text section. Other code
        # sections have overlapping runtime entries; quarantine them instead
        # of guessing precedence or interpreting their contents as functions.
        text = next(s for s in self.pe.sections if s.Name.rstrip(b'\0') == b'.text')
        ranges = [RuntimeRange(e.struct.BeginAddress,e.struct.EndAddress,e.struct.UnwindData)
                  for e in self.pe.DIRECTORY_ENTRY_EXCEPTION]
        selected = [r for r in ranges if text.VirtualAddress <= r.begin < r.end <= text.VirtualAddress+text.Misc_VirtualSize]
        self.excluded_ranges = len(ranges)-len(selected)
        self.index = UnwindIndex(selected, self.pe.get_data)
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64); self.cs.detail = True
        self.cache = {}

    def instructions(self, rva):
        root = self.index.root(rva)
        if root is None:
            return []  # A leaf needs a separately validated explicit bound.
        if root not in self.cache:
            result = []
            for r in self.index.groups[root]:
                raw = self.pe.get_data(r.begin, r.end-r.begin)
                decoded = list(self.cs.disasm(raw, r.begin))
                if not decoded or decoded[-1].address+decoded[-1].size != r.end:
                    raise ValueError(f'Incomplete instruction decoding at {r.begin:#x}')
                result.extend(decoded)
            self.cache[root] = result
        return self.cache[root]
