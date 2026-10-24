"""Read-only ESP/ESM inspection for the isolated LoreRim diagnosis."""
import json, mmap, struct, zlib
from pathlib import Path


def fields(data):
    pos, extended = 0, None
    while pos + 6 <= len(data):
        tag, size = struct.unpack_from('<4sH', data, pos)
        pos += 6
        if tag == b'XXXX':
            extended = struct.unpack_from('<I', data, pos)[0]
            pos += size
            continue
        size = extended if extended is not None else size
        extended = None
        yield tag, data[pos:pos+size]
        pos += size


def records(path, wanted):
    with open(path, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            def walk(start, end):
                pos = start
                while pos + 24 <= end:
                    sig, size = struct.unpack_from('<4sI', mm, pos)
                    if sig == b'GRUP':
                        label = mm[pos+8:pos+12]
                        group_type = struct.unpack_from('<i', mm, pos+12)[0]
                        if group_type != 0 or label in wanted:
                            yield from walk(pos+24, pos+size)
                        pos += size
                    else:
                        if sig in wanted or sig == b'TES4':
                            flags, fid = struct.unpack_from('<II', mm, pos+8)
                            data = mm[pos+24:pos+24+size]
                            if flags & 0x40000:
                                data = zlib.decompress(data[4:])
                            yield sig, fid, dict(fields(data)), list(fields(data))
                        pos += 24 + size
            yield from walk(0, len(mm))


def z(data):
    return data.rstrip(b'\0').decode('utf-8', errors='replace')


if __name__ == '__main__':
    lab = Path('L:/LoreRim')
    mods = [s[1:].strip() for s in
            (lab/'profiles/LoreRim LAN Test/modlist.txt').read_text(encoding='utf-8-sig').splitlines()
            if s.startswith('+')]
    # MO2 modlist is highest-priority first.
    files = {}
    for name in mods:
        root = lab/'mods'/name
        if root.exists():
            for p in root.iterdir():
                if p.is_file() and p.suffix.lower() in ('.esm', '.esp', '.esl'):
                    files.setdefault(p.name.lower(), p)
    selected = ('requiem.esp', 'requiem - alchemy redone.esp',
                'requiem for the indifferent.esp', 'dvsSurvivalTweaks.esp'.lower(),
                'survivalmodeimproved.esp')
    for name in selected:
        path = files.get(name)
        if not path:
            print('MISSING', name)
            continue
        print('FILE', str(path))
        for sig, fid, fs, all_fields in records(path, {b'ALCH', b'MGEF', b'SPEL', b'IMAD', b'GLOB'}):
            edid = z(fs.get(b'EDID', b''))
            if (fid & 0xFFFFFF in (0x2C35A, 0xF693F) and sig == b'ALCH') or any(
                    word in edid.lower() for word in ('alcohol', 'drunk', 'exhaustion', 'thirststage')):
                obj = {'type': z(sig), 'form': hex(fid), 'edid': edid,
                       'name': z(fs.get(b'FULL', b'')),
                       'description': z(fs.get(b'DNAM', b'')) if sig == b'MGEF' else ''}
                if sig == b'ALCH':
                    obj['effects'] = [hex(struct.unpack('<I', b)[0])
                                      for t, b in all_fields if t == b'EFID']
                    obj['magnitudes_duration'] = [struct.unpack('<fII', b[:12])
                                                 for t, b in all_fields if t == b'EFIT']
                if sig == b'GLOB':
                    obj['value'] = struct.unpack('<f', fs[b'FLTV'])[0]
                print(json.dumps(obj))
