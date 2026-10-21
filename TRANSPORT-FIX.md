# Large plugin-list connection correction

The first connection was refused by ModPolicy. This was not evidence that 1,422
mods needed installation: the server/profile each listed 3,492 plugins, while
the rejected handshake contained 1,422 empty names and the corresponding missing
server names. One filename also differs in capitalization between the current
MO2 profile and the older server list; exact runtime policy validation remains
necessary after correcting transmission.

## Cause and evidence

STR v1.8.3 `TransportService::Send` starts a 64 KiB Buffer inside a 256 KiB
thread-local ScratchAllocator. Buffer growth allocates a new region and copies
the previous contents, but ScratchAllocator::Free does not reclaim space until
Reset. Repeated 2 KiB growth consumes the pool well before the full list is
serialized. Buffer::Resize returns false, but the mod serializer ignores writer
failures and still sends a packet with the full declared count. Readers then
produce empty names from missing data.

The installed executable was inspected using its PE exception-function boundaries
and instruction disassembly. The normal Send routine and its authentication
inline copy both call the same Buffer and ScratchAllocator constructors and
serialize/send/reset in the sequence shown by v1.8.3 source. This change affects
network serialization allocation sizes, not game structures, hooks or offsets.

A native regression compiles the actual unchanged TiltedCore v0.2.9 Buffer.cpp
and ScratchAllocator.cpp. A standard heap adapter supplies their default allocator;
the tested Buffer/growth/pool behavior is upstream code. With the lab's 3,492
names, the original capacities fail at entry 2,071 after 69,620 bytes. The revised
capacities round-trip all 3,492 IDs, flags and names in 129,470 bytes, with
1,835,008 bytes of pool space remaining. This reproduces the allocation failure
without invoking Skyrim and does not replace an actual connection test.

Runtime status: the corrected executable launched and reached the LoreRim menu.
A new server connection attempt is pending because the game did not reliably
respond to automated menu input. No accepted connection is claimed yet.

## Installed correction and rollback

`transport_fix.py` changes four size immediates in the exact installed STR 1.8.3
1.6.1170 executable: both Send copies use a 256 KiB initial buffer and 2 MiB
scratch pool. The patch changes four bytes total. Packet format, mod count limit,
version identity, server policy and mod content remain unchanged.

Original SHA256:
`27815f3be0375a5eeb52be935da0339b8dfe853c7edfbeaafd47c1bf267e8521`

Patched SHA256:
`b4316ade189c8bd988a747ead72953232138ac34b39d20b1cbb6360f2627e49e`

Verified instruction RVAs and file offsets:

| Site | RVA | File offset | Old / new size |
|---|---|---|---|
| Inlined authentication pool | 0x4066AABD | 0x2CC4BD | 256 KiB / 2 MiB |
| Inlined authentication buffer | 0x4066AAF3 | 0x2CC4F3 | 64 KiB / 256 KiB |
| Normal Send pool | 0x4066AE75 | 0x2CC875 | 256 KiB / 2 MiB |
| Normal Send buffer | 0x4066AEAE | 0x2CC8AE | 64 KiB / 256 KiB |

With game clients closed, use the marked isolated lab:

```powershell
python transport_fix.py 'D:\LoreRim-LAN\LoreRim'
python transport_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
```

The installer rejects unknown executables, changed backups, running clients,
linked/shared targets and original/overlapping installations. It preserves the
original under `transport-fix-backup/SkyrimTogether.exe.original`. No upstream
executable is redistributed. Apply the same correction on both test PCs and
regenerate parity manifests.

This is tested for this lab's 3,492-entry list, not every possible larger list or
packet type. Connecting alone does not establish multiplayer gameplay correctness.

## Reproduce the native regression

Use Zig 0.14.1 and an unmodified TiltedCore v0.2.9 checkout at
`b5aa9203dc47e3ced49ca60e65d1bf4409501f03`. Supply a UTF-8 file containing one active
plugin name per line, without comments or MO2 `*` prefixes:

```powershell
python native/test_transport_buffer.py --compiler '<zig.exe>' --core '<TiltedCore checkout>' --plugins '<plugin-names.txt>' --output 'build/transport_buffer_test.exe'
```

Sources inspected:
[STR v1.8.3 TransportService](https://github.com/tiltedphoques/TiltedEvolution/blob/v1.8.3/Code/client/Services/Generic/TransportService.cpp),
[mod serialization](https://github.com/tiltedphoques/TiltedEvolution/blob/v1.8.3/Code/encoding/Structs/Mods.cpp),
[TiltedCore v0.2.9 Buffer](https://github.com/tiltedphoques/TiltedCore/blob/v0.2.9/Code/core/src/Buffer.cpp),
[ScratchAllocator](https://github.com/tiltedphoques/TiltedCore/blob/v0.2.9/Code/core/src/ScratchAllocator.cpp).
