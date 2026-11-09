"""Bounded, read-only APFS metadata inspection. Never mount or write a disk.

Only supported leaf object maps and valid checksummed objects are used. Other
layouts produce unknown metadata. See Apple's APFS reference and asahi-bless.
"""
import os
from pathlib import Path
import struct
import uuid

class Unsupported(ValueError):
    pass

def u16(data, offset): return struct.unpack_from('<H', data, offset)[0]
def u32(data, offset): return struct.unpack_from('<I', data, offset)[0]
def u64(data, offset): return struct.unpack_from('<Q', data, offset)[0]

def checksum_ok(data):
    if len(data) % 4 or len(data) < 32:
        return False
    a = b = 0
    mod = 0xffffffff
    for (word,) in struct.iter_unpack('<I', data[8:]):
        a = (a + word) % mod
        b = (b + a) % mod
    low = (mod - ((a + b) % mod)) % mod
    high = (mod - ((a + low) % mod)) % mod
    return u64(data, 0) == (high << 32 | low)

def read_object(stream, block, size, count):
    if not 0 <= block < count or size not in [4096, 8192, 16384, 32768, 65536]:
        raise Unsupported('APFS object address or block size is unsupported')
    stream.seek(block * size)
    data = stream.read(size)
    if len(data) != size or not checksum_ok(data):
        raise Unsupported('APFS object checksum failed')
    return data

def scan_container(stream):
    stream.seek(0)
    header = stream.read(1408)
    if len(header) < 1408 or header[32:36] != b'NXSB':
        raise Unsupported('Not an APFS container')
    size, count = u32(header, 36), u64(header, 40)
    sb = read_object(stream, 0, size, count)
    desc_count = u32(sb, 104)
    desc_base = u64(sb, 112)
    if desc_count & 0x80000000 or desc_count > 4096:
        raise Unsupported('Unsupported checkpoint descriptor layout')
    best = sb
    for block in range(desc_base, desc_base + desc_count):
        try:
            candidate = read_object(stream, block, size, count)
        except Unsupported:
            continue
        if candidate[32:36] == b'NXSB' and u64(candidate, 16) > u64(best, 16):
            best = candidate
    sb = best
    omap = read_object(stream, u64(sb, 160), size, count)
    node = read_object(stream, u64(omap, 48), size, count)
    flags, level, keys = u16(node, 32), u16(node, 34), u32(node, 36)
    if level != 0 or not flags & 4 or keys > size // 4:
        raise Unsupported('Only fixed-size leaf object maps are supported')
    toc = 56 + u16(node, 40)
    key_start = toc + u16(node, 42)
    val_end = size - (40 if flags & 1 else 0)
    objects = {}
    for index in range(keys):
        entry = toc + 4 * index
        if entry + 4 > size:
            raise Unsupported('Invalid object-map table')
        key = key_start + u16(node, entry)
        val = val_end - u16(node, entry + 2)
        if key + 16 > size or val < 56 or val + 16 > size:
            raise Unsupported('Invalid object-map record')
        oid, xid = u64(node, key), u64(node, key + 8)
        if xid <= u64(sb, 16) and not u32(node, val) & 1:
            if oid not in objects or xid > objects[oid][0]:
                objects[oid] = (xid, u64(node, val + 8))
    volumes = []
    for index in range(min(u32(sb, 180), 100)):
        oid = u64(sb, 184 + index * 8)
        if not oid or oid not in objects:
            continue
        data = read_object(stream, objects[oid][1], size, count)
        if data[32:36] != b'APSB' or u16(data, 964) != 1:
            continue
        name = data[704:960].split(b'\0', 1)[0].decode('utf-8', errors='strict')
        vg = str(uuid.UUID(bytes=data[1008:1024]))
        if vg == str(uuid.UUID(int=0)):
            continue
        incompatible = u64(data, 56)
        # A sealed System volume is a macOS candidate, not proof of boot health.
        sealed = bool(incompatible & 0x20) and not incompatible & 0x10
        volumes.append({'name': name, 'vg_uuid': vg, 'sealed_system': sealed})
    return volumes

def system_metadata():
    found = []
    # Match asahi-bless's internal disk; do not accept user-supplied devices.
    for partition in sorted(Path('/sys/class/block').glob('nvme0n1p*')):
        if not (partition / 'partition').exists():
            continue
        try:
            device = Path('/dev') / partition.name
            with device.open('rb', buffering=0) as stream:
                for volume in scan_container(stream):
                    volume['partition'] = partition.name
                    found.append(volume)
        except (OSError, Unsupported, UnicodeError, struct.error, OverflowError):
            continue
    return found
