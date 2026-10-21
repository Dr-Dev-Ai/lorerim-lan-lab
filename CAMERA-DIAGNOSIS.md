# Camera startup investigation — 2026-10-20

Status: first failing scan explained by installed-binary and live-memory evidence.
**No native fix applied. No main menu or gameplay validation.**

## Reproduction

The existing physical lab was launched through portable MO2's `LoreRim LAN Test`
profile, with its 3,891 active entries retained. The lab's existing `L:` mapping
was missing in the new session; restoring it to the isolated directory resolved
MO2's downloads-path error. The original installation was not modified.

The new STR process displayed exactly:
`[ERROR] Unknown pattern: 0f28c1f30f5ec60f28f0`.
SKSE's new log ended at `loading plugin "Improved Alternate Conversation Camera"`.
The camera log contained `Load`. This was a blocked initialization dialog, not a
new captured crash dump. Existing crash reports predated this attempt.

KiHalloc and KiENBExtender were both present in the live module inventory.
The staged KiHalloc matched its installed source SHA256:
`c46ec36030108e52a8fa689fd149c0dc7ef0cb49c59fa7649550f8e715b78936`.
The existing loader fix therefore needed no change.

## Evidence

Installed camera DLL (both original and lab), version 1.2.0.0:
`fd09d76ec7a3288787fbf3f0c1bfba69b43c12e73f48f3b7a146e4986430acb7`.

Lab SkyrimSE.exe:
`c434208894f07f604b852f29b8edc3a58c4de63de783373733e72b2b73f33be9`.

Read-only disassembly with pefile 2024.8.26 and Capstone 5.0.9 established the
following in the **installed Improved DLL**, rather than just its older ancestor:

| Camera DLL RVA | Observation |
|---|---|
| `0xC992`–`0xC9A2` | Builds the ten requested bytes as three stack immediates |
| `0xC9A9` | Calls imported GetModuleHandleW with null argument |
| `0xC9DD` | Calls imported K32GetModuleInformation |
| `0xCA01` | Calls scanner at RVA `0x16380`, using image base and SizeOfImage |
| `0x163EE` | Scanner calls imported VirtualQuery |
| `0x16402` | Requires MEM_COMMIT (`0x1000`) |
| `0x16410` | `test al, 0x20` tests the protection field |
| `0x16412` | Skips region if the test is zero |
| `0x16414`–`0x16418` | Rejects PAGE_GUARD |
| `0x16429` onward | Searches for a ten-byte pattern |

While the error dialog remained open, the read-only probe scanned the enumerated
SkyrimTogether.exe image at base `0x140000000`, extent `0x409BF000`.
It found one occurrence of the requested bytes at image RVA `0x36F236` on a
committed page with protection `0x40` (PAGE_EXECUTE_READWRITE). No readable-region
read errors were reported. These are diagnostic RVAs, **not approved hook addresses**.

`0x40 & 0x20 == 0`: the installed scanner excludes the page holding this match.
This provides a concrete explanation for the observed first scan failure.
The static file search's absence of a contiguous pattern was not evidence that
the runtime pattern was missing: the DLL constructs its search bytes and STR's
live image contains the target bytes.

## Reproduce the observation

With the lab's error dialog still open, obtain its SkyrimTogether.exe process ID:

```powershell
Get-Process SkyrimTogether | Select-Object Id, Path
python camera_probe.py <PID> camera-capture.json
```

Requires 64-bit Python on Windows; no third-party packages for the live probe.
The default target is SkyrimTogether.exe; `--module` selects another exact module
basename. The probe requests only query/read access, never injects, changes page
protection, patches or writes target memory. It does not save raw memory.
Reports contain local paths; review before sharing. Existing output is never
overwritten. Exit 3 denotes a capture/read failure, exit 0 a completed observation,
**not compatibility**. Capture is non-atomic. Guard/noaccess/uncommitted regions and
matches crossing protection-region boundaries are excluded and documented.

Run all regression and Windows self-probe tests:

```powershell
python -m unittest discover -s . -p 'test_*.py' -v
```

16 tests passed on Windows x64, including bounded reads, overlapping and
chunk-boundary matches, inaccessible/short reads, protection flags, evidence
preservation, failure exit status and a real read-only self-process capture.
The eight existing preflight/dependency tests also remained passing.

## Remaining work

The evidence supports correcting the scanner's readable-executable protection
predicate. It does **not** validate every later signature, resolved address,
instruction overwritten by a hook, or interaction with STR. Broadly replacing
all `0x20` constants or switching game page protections would be unjustified.
No such patch was applied, and no camera features or other mods were disabled.

A matching Improved 1.2 source/build has not been located. The available
[original camera source](https://github.com/NasiRawon/AlternateConversationCamera)
does not establish preservation of Improved's added features. The
[Improved mod page](https://www.nexusmods.com/skyrimspecialedition/mods/68210)
lists STR as incompatible. A feature-preserving native repair still requires
matching source or a complete binary-level audit of affected scans and hooks,
followed by isolated single-player/STR camera regression tests. No C++ build was
performed in this session.

The disposable blocked game process was stopped after capture. MO2's Root
Builder logged successful sync, restore and clear. Both remote devices were
offline. Main menu, two-PC connection, combat/quests/saves synchronization and
performance remain unverified; follow TESTING.md only after startup is resolved.
