# dosemetha startup correction — 2026-10-20

The isolated lab now loads the unchanged dosemetha DLL before BSA Memory Map.
Its `GetLocationsCandidates` hook installs successfully. No mod was disabled.

## Install / rollback

Close game clients, then use a marked, physically isolated lab:

```powershell
python dosemetha_fix.py 'D:\LoreRim-LAN\LoreRim'
python dosemetha_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
```

Refresh MO2's file list before launching. The change renames only
`mods/Don't send me there again (dosemetha)/SKSE/Plugins/dosemetha.dll`
to `000_dosemetha.dll`. Restore reverses that rename. The plugin's internal
name and code are unchanged. The installer pins SHA256
`e64dc70941dbe5cfa97b3198a9a4ec376f50cfaf9de8e73bbec7d372cb0a44a7` and rejects
unknown builds, duplicate names, running clients, shared files and original or
overlapping installations. Apply to both PCs and regenerate parity manifests.
This is opt-in, not silently applied by Setup-Lab.ps1.

## Evidence and limits

Before the change, the dialog and dosemetha log reported:
`main.cpp(110): Failed to hook GetLocationsCandidates`.

Read-only disassembly identified Address Library ID 25118, resolving on this
1.6.1170 runtime to `0x1403D5420`. The live CommonLib lookup table agreed. The
function entry contained ordinary instructions rather than a pre-existing jump.
The installed MinHook allocator searched within +/- `0x40000000` of the target
for a free, allocation-granularity-aligned block. A VirtualQueryEx inventory found
no 64-KiB-aligned position with room for the required 4-KiB allocation. Expanding
the diagnostic search to +/- `0x7FFF0000` also found none; no allocation-range
binary patch was attempted.

GetMappedFileNameW identified large texture BSA views occupying the low address
range, including 4K Nordic Murals, Additional Dremora Faces and Aqua. The installed
BSAMemoryMap log separately reported failure to allocate a trampoline and a
Detours error. Upstream Faster File Copy source initializes archive mapping
before installing its hooks. The actual MinHook return code was not captured;
allocation exhaustion is supported by the memory inventory and controlled
early-load success, not by a captured return-code trace.

After the filename-only change:

- SKSE logged `plugin 000_dosemetha.dll (00000001 dosemetha 01010000) loaded correctly (handle 1)`.
- The dosemetha log no longer reported hook failure.
- Live target bytes changed to a jump to relay `0x13FFB0FD4`; the relay's absolute
  destination matched dosemetha's own handler at module RVA `0x15B30`.
- The stored original-function pointer was `0x13FFB0FC0`. Its trampoline preserved
  the displaced six bytes and jumped back to `0x1403D5426`.
- The disk DLL hash remained unchanged, and the original LoreRim installation's
  DLL retained its original name and bytes.
- All 28 tooling tests passed, including rename/restore, idempotence, duplicate
  refusal, unsupported binary refusal, running-client refusal and shared-file
  protection. Synthetic tests do not establish quest correctness.

The addresses above identify this diagnostic session only. They are not offsets
to patch in other builds. Radiant quest selection still requires gameplay tests.

## Remaining blocker

Follow-up: [BSA-MAPPING-FIX.md](BSA-MAPPING-FIX.md) records the subsequently
installed allocation adapter and successful DynDOLOD/BSA hook initialization.
The adapter now allows the unchanged DLL to load under its canonical
`dosemetha.dll` filename; the early rename has been restored in this lab.
The following records the prior failing launch.

Startup continued past dosemetha, then stopped at DynDOLOD:
`SKSE/Trampoline.cpp(54): failed to create trampoline`.
BSAMemoryMap also still logs its own hook allocation failures. No main menu,
multiplayer connection or gameplay was reached. The blocked test process was
stopped after preserving evidence; the installed filename correction remains.

Moving individual plugins earlier is not a general repair for archive mappings
consuming nearby hook-address space. A broader repair should keep archive/cache
views away from the executable's relative-branch range or reserve and manage
hook allocation space before mapping. It must preserve the cache, graphics and
other mods and be built/tested before being described as fixed. The current
environment has no detected MSVC/Clang/CMake/native SDK toolchain, and no broader
native repair was installed.

Source inspected: [Faster File Copy](https://github.com/1001Bits/Faster-File-Copy),
including commit `9cd98aa` (v1.6.0) and current `fac613b` (v1.7.0).
