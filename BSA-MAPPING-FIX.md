# BSA mapping and DynDOLOD startup correction

The isolated lab now reaches the LoreRim main menu through Skyrim Together.
DynDOLOD initializes successfully. The installed BSA plugin
and all archive/cache features remain enabled. The correction uses a small
source-built adapter around the existing Faster File Copy / BSAMemoryMap 1.6.0
DLL. No third-party mod binary is included in the adapter package.

## What changed

The original plugin maps hundreds of BSA archives before installing hooks. On
this STR process those views occupied the space required for relative-branch
trampolines. The adapter redirects only the original plugin's read-only
`MapViewOfFile` requests through the documented Windows `MapViewOfFile3` API,
with a lowest address of 64 GiB. A live handle audit also found 277 aliases of
the same CommonLib Address Library table. To keep those aliases away from hook
space, the adapter intercepts the process MapViewOfFile API using MinHook 1.3.4,
queries the supplied section object's name and redirects only these three exact
table names for the target runtime:

- `CommonLibSSEOffsets-v2-1-6-1170-0`
- `Shared-AddressLibrary-1-versionlib-1-6-1170-0`
- `COMMONLIB_IDDB_OFFSETS_1_6_1170_0`

Selected shared views retain their read/write permissions, offsets, contents
and section sharing while moving above 64 GiB. Other process mapping requests
use the original API. No Steam, graphics, MO2 or other named mappings are selected.

The original plugin's private 64-byte trampoline fallback searches only above
the executable. STR occupies that range. When its exact first request fails,
the adapter uses `VirtualAlloc2` to allocate within 1 GiB below the executable.
Other VirtualAlloc requests pass through unchanged. The original plugin writes
and manages its own trampoline using its existing code.

Three import-table entries inside the hash-pinned native plugin change:
MapViewOfFile, VirtualAlloc and GetModuleFileNameA. The last preserves the original
INI path/name when the original DLL is loaded with a backup suffix. No engine
instructions, offsets, mod settings, archives, graphics or cache files are patched.
The process API hook uses the version-pinned MinHook implementation to relocate
Windows API instructions; it does not patch Skyrim engine instructions. The
adapter forwards the native SKSE Query/Load entry points and preserves its
848-byte version metadata exactly. It pins itself before the native plugin can
retain callbacks. Initialization runs outside DllMain.

## Install and restore

Close game clients. Use a marked physical lab and the tested adapter supplied
with this package:

```powershell
python bsa_guard_fix.py 'D:\LoreRim-LAN\LoreRim' --adapter '.\adapter\BSAMemoryMap.dll'
python blink_fix.py 'D:\LoreRim-LAN\LoreRim'
python alttab_fix.py 'D:\LoreRim-LAN\LoreRim'
```

The installer retains the original byte-identical DLL beside the adapter as
`BSAMemoryMap.native.bin`, which SKSE does not enumerate as a plugin. That native
file must remain present. The original `BSAMemoryMap.ini` remains the settings
source. The adapter's diagnostic log is `BSAMemoryMap.guard.log` next to the DLL
in MO2's virtual view; writes may appear under the lab's overwrite folder.
The native log remains in the game's normal SKSE log directory.

Rollback with clients closed:

```powershell
python bsa_guard_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
python blink_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
python alttab_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
```

Installers reject unknown binaries, changed backups, linked/shared files,
running clients and original/overlapping installations. They retain rollback
bytes and verify installed content. The correction is opt-in for this exact
lab combination, not automatically applied by Setup-Lab.ps1. Both LAN PCs must
use the same build and regenerate full parity manifests before connecting.

Native DLL SHA256:
`05e073b2083c2fb491902e95bbc16a06eaf75187354e552100decdc9e74fc640`

Tested adapter SHA256:
`2599e9475852a61a26a8e22c85a380e34c615b119d0223bc56fe574c8c4163c4`

The adapter verifies the original DLL hash again before loading it. Import
addresses must match the expected Windows APIs. Unsupported Windows APIs or an
unexpected native build stop adapter initialization before native SKSE loading.
Failed high-address mappings do not fall back into the game's nearby hook space.

## Player Eyes Blink Fix

Startup exposed `[ERROR] Unknown pattern: 0fb691e50b0000` in Player Eyes Blink Fix
1.4 AE. The live pattern occurs once at game-image RVA `0x79F3C8` on an RWX page.
The installed DLL and upstream source use the same RX-only scan predicate as the
previous camera blocker. Disassembly verified two compiled scanner variants at
DLL RVAs `0x618B` and `0x6557`, with committed-memory checks and guard rejection.
`blink_fix.py` changes only their protection-mask bytes at file offsets `0x558C`
and `0x5958` from `0x20` to `0x60`, retaining all other bytes and rollback data.

Original SHA256:
`ed52173ed08a2c77b28d525b086b791b6202151e4635eb2d62935e7354913a49`

Patched SHA256:
`ccc45899a25254c3e1872239d977d286498bc1060705526282b64e028ad81c57`

## Better AltTab 1.0.1 callback

After form loading, Better AltTab displayed `Trampoline.cpp(54): failed to create
trampoline`. A thread-stack capture placed the blocked callback in its second
`Trampoline::create(64)` call at DLL RVA `0x6E0A`, immediately before resolving
the cursor function and installing its Detours hook. Upstream's `v1.0.2` source,
commit `e6e2939` ("Remove unused code"), removes this unused second allocation.
Its actual cursor hook uses Detours; its audio hook already allocated the shared
trampoline during plugin load. The public releases endpoint had no 1.0.2 binary.

`alttab_fix.py` applies the equivalent minimal correction to the exact installed
1.0.1 binary: the five-byte call at file offset `0x620A` becomes five NOPs. The
audio hook, cursor hook, settings, relocation lookup and subsequent Detours calls
remain intact. The original is retained under `alttab-fix-backup` for restoration.

Original SHA256:
`662c15a7f586becbecc9ee156167b1c0075009429a5f278157fc847844641254`

Patched SHA256:
`6b76f6c54abce6afdd2675ad95c1454a7ff9d907be22dd4d76e98174ea876882`

Game-data heaps later exhausted nearby space for the actual cursor Detours hook
as well. The adapter reserves four 64 KiB slots within 512 MiB below the executable
before form loading. These are virtual reservations with no committed pages.
Only the hash-pinned patched Better AltTab DLL receives two adapted imports:
VirtualQuery reports an unused owned slot as available to its allocator, and
VirtualAlloc commits that reservation when it receives the exact base, a size
up to 64 KiB, MEM_RESERVE|MEM_COMMIT and PAGE_EXECUTE_READWRITE. Other modules
see the real reservation and cannot consume it. Other Better AltTab queries and
allocations pass through unchanged. Claimed slots subsequently report their real
committed state. This preserves the plugin's existing Detours hook emitter.

This mirrors the source fix's removal of the allocation call; it is not a full
update to Better AltTab 1.0.2. Window-focus, background audio and cursor behavior
still need in-game regression testing.

## Verification

- Native C adapter compiled with Zig 0.14.1 for Windows x64, warnings treated as
  errors. Compiler download verified against the publisher's SHA256.
- 38 tooling tests passed, including installer rollback, backup preservation,
  unknown adapter, changed user file, running client and hardlink refusal.
- Eleven native Windows integration tests passed: concurrent high mappings,
  whole-view bytes/protection, offsets/size, invalid offset behavior, writable
  shared-view semantics, native version metadata, original INI path and the
  below-executable trampoline allocation, exact table-name selection and high
  shared read/write view contents, and private Better AltTab slot reservation,
  visibility and commitment. A separate corrupted-native rejection
  smoke check also passed. These tests do not call native SKSEPlugin_Load.
- The live game reported the camera, dosemetha, BSAMemoryMap, DynDOLOD and Player
  Eyes Blink Fix loaded correctly, completed the full SKSE plugin initialization,
  and opened its render window for ENB shader compilation.
- DynDOLOD's own log reported `Trampoline initialized`, `DynDOLOD Patch installed`
  and save/load handler installation.
- The latest BSAMemoryMap native log no longer reported trampoline or Detours
  failures. The adapter logged a successful private trampoline allocation and
  successful native SKSEPlugin_Load.
- The final adapter reserved Better AltTab hook space, and the live plugin log
  reported both `WindowProc hook installed` and `ToggleCursor hook installed`.
  The adapter confirmed that Better AltTab consumed one owned reservation.
- A live VirtualQueryEx/GetMappedFileNameW audit identified 774 BSA views; all
  observed views were at or above 64 GiB.

Early unsuccessful adapter iterations were stopped and corrected: explicit
mapping alignment was rejected by Windows, and the first in-game attempt exposed
CommonLib's writable mapping requirement. Neither unsuccessful build is the
installed/tested final adapter. The intermediate archive-only adapter cleared
DynDOLOD but left late allocations under pressure from shared Address Library
aliases; those aliases are handled by the final named-section adapter. Evidence
from failed attempts remains retained.

On the final launch (process 21272), the LoreRim main menu appeared after full
form/animation loading, with New and Quit available. Screenshot and startup logs
were retained. No error dialog was dismissed to reach the menu.
Dialogue, radiant quests, saves, long-term cache behavior, graphics correctness
and multiplayer synchronization still require their runtime acceptance tests.
Follow TESTING.md before treating this as a multiplayer compatibility pass.

## Build and test from source

`native/build_bsa_guard.py` requires Python, pefile, Zig 0.14.1 and the locally
installed exact native DLL, plus an unchanged MinHook v1.3.4 checkout at commit
`c3fcafdc10146beb5919319d0683e44e3c30d537`. MinHook's redistribution notices are
included in `native/MINHOOK-LICENSE.txt`. The builder extracts only native
compatibility metadata and
builds this repository's adapter source:

```powershell
python native/build_bsa_guard.py --compiler '<zig.exe>' --native '<installed native DLL>' --output 'build/BSAMemoryMap.dll' --minhook '<MinHook checkout>'
python native/test_bsa_map_guard.py --adapter 'build/BSAMemoryMap.dll' --native '<installed native DLL>'
python -m unittest discover -s . -p 'test_*.py' -v
```

The build writes a report with compiler version, source, native, metadata and
adapter hashes and the command used. Compiler/linker output can vary between
builds; the installer deliberately pins the tested packaged artifact. A rebuilt
adapter needs its own tests, runtime validation and installer-hash update.

References: [Faster File Copy v1.6.0 source](https://github.com/1001Bits/Faster-File-Copy/tree/9cd98aa),
[Player Eyes Blink Fix source](https://github.com/NasiRawon/PlayerEyesBlinkFix),
[Better AltTab unused-allocation removal](https://github.com/epinter/better-alttab/commit/e6e2939),
[MinHook v1.3.4](https://github.com/TsudaKageyu/minhook/tree/v1.3.4),
[SKSE Plugin API](https://github.com/ianpatt/skse64/blob/master/skse64/PluginAPI.h),
[MapViewOfFile3](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3),
[VirtualAlloc2](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2).
