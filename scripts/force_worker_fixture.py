"""Private sparse fixtures for the original 0x851f00 worker (no code bytes).

Fixtures are trusted local research inputs, not portable vehicle snapshots.
V2 pins the executable digest and preserves only bytes actually accessed by
one complete call. Native execution additionally requires offline replay.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

from pinned_build import SHA

PAGE = 4096
MAGIC = b"TMFWFX2\0"
ENTRY = 0x851F00
SYNTHETIC = (
    (0x200000000, 0x10000),
    (0x300000000, 0x4000),
    (0x400000000, 0x20000),
    (0x500000000, 0x1000),
)


@dataclass(frozen=True)
class DataPage:
    address: int
    mask: bytes
    initial: bytes
    expected: bytes


@dataclass(frozen=True)
class Fixture:
    sha256: str
    base: int
    image_size: int
    timestamp: int
    float_bits: int
    mxcsr: int
    r9: int
    force_address: int
    vehicle_address: int
    context: bytes
    code_pages: tuple
    data_pages: tuple


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_fixture(path, pe):
    path = Path(path)
    require(0 < path.stat().st_size <= 8 * 1024 * 1024, "Fixture size bound")
    raw = path.read_bytes()
    at = 0

    def take(n):
        nonlocal at
        value = raw[at : at + n]
        require(len(value) == n, "Truncated fixture")
        at += n
        return value

    def unpack(fmt):
        return struct.unpack(fmt, take(struct.calcsize(fmt)))

    require(take(8) == MAGIC and unpack("<I")[0] == 2, "Unknown fixture format")
    require(take(32).hex() == SHA, "Fixture build differs from pinned executable")
    base, image_size, nc, nd, ns = unpack("<Q4I")
    require(
        base >= 0x100000000 and base < 0x7FFF00000000 and base % 65536 == 0,
        "Invalid original image address",
    )
    require(
        image_size == pe.OPTIONAL_HEADER.SizeOfImage
        and 0 < nc <= 512
        and 0 < nd <= 512
        and ns == 88,
        "Invalid fixture extents",
    )
    timestamp, float_bits, mxcsr, r9, forces, vehicle = unpack("<QII3Q")
    require(
        mxcsr == 0x1F80 and float_bits == 0x3C23D70B,
        "Unsupported worker interval/MXCSR",
    )
    context = take(ns)
    code = unpack("<" + "I" * nc)
    require(
        len(set(code)) == nc and ENTRY & ~4095 in code,
        "Duplicate/missing worker code page",
    )
    for rva in code:
        require(
            rva % PAGE == 0
            and any(
                s.Name.rstrip(b"\0") == b".text"
                and s.Characteristics & 0x20000000
                and s.VirtualAddress <= rva
                and rva + PAGE <= s.VirtualAddress + s.SizeOfRawData
                for s in pe.sections
            ),
            "Code page outside ordinary .text",
        )
        require(len(pe.get_data(rva, PAGE)) == PAGE, "Truncated original code page")
    pages = []
    seen = {base + rva for rva in code}
    for _ in range(nd):
        (address,) = unpack("<Q")
        mask, initial, expected = take(PAGE), take(PAGE), take(PAGE)
        require(address % PAGE == 0 and address not in seen, "Duplicate/unaligned page")
        require(
            base <= address
            and address + PAGE <= base + image_size
            or 0x100000000 <= address
            and address + PAGE <= 0x40000000000,
            "Data page exceeds owned address domain",
        )
        require(
            not any(a < address + PAGE and address < a + n for a, n in SYNTHETIC),
            "Data collides with owned replay context/TLS/stack",
        )
        require(
            all(
                m in (0, 1) and (m or a == b == 0)
                for m, a, b in zip(mask, initial, expected)
            ),
            "Unaccessed source bytes retained or invalid mask",
        )
        seen.add(address)
        pages.append(DataPage(address, mask, initial, expected))
    require(at == len(raw), "Trailing fixture data")
    return Fixture(
        hashlib.sha256(raw).hexdigest(),
        base,
        image_size,
        timestamp,
        float_bits,
        mxcsr,
        r9,
        forces,
        vehicle,
        context,
        code,
        tuple(pages),
    )


def encode_fixture(
    base,
    image_size,
    timestamp,
    float_bits,
    mxcsr,
    r9,
    force_address,
    vehicle_address,
    context,
    code_pages,
    data_pages,
):
    out = bytearray(MAGIC + struct.pack("<I", 2) + bytes.fromhex(SHA))
    out += struct.pack(
        "<Q4I", base, image_size, len(code_pages), len(data_pages), len(context)
    )
    out += struct.pack(
        "<QII3Q", timestamp, float_bits, mxcsr, r9, force_address, vehicle_address
    )
    out += context + struct.pack("<" + "I" * len(code_pages), *code_pages)
    for page in data_pages:
        out += (
            struct.pack("<Q", page.address) + page.mask + page.initial + page.expected
        )
    return bytes(out)
