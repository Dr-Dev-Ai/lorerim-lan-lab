# Guided Windows installer

Download `LoreRim-Together-Installer.zip` from the
[v0.2.0 experimental release](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/tag/v0.2.0-experimental).
Extract the complete ZIP, then double-click **Install LoreRim Together.exe**.
There are no terminal commands or separate Python installation steps.

The wizard detects common LoreRim folders, lets the player choose another folder
or destination drive, and checks the runtime, source plugin ordering, native
plugin hashes, closed applications and available disk space. It downloads pinned
official STR 1.8.3 and JContainers 4.2.13.1 archives, physically copies the
existing installation without its download cache or old saves, prepares the LAN
profile, stages KiLoader dependencies, applies all six fixes, verifies the
result and creates desktop play/help shortcuts. The original stays separate.

The ZIP includes the official Python 3.12.10 embeddable runtime and license,
our tested BSA adapter and MinHook license. It does not include game assets or
original mod DLLs. Python is private to this folder: no administrator access,
PATH changes, terminal commands, PowerShell policy changes or pip are required.
The native frontend uses Windows' .NET Framework and creates shortcuts through
the Windows scripting COM API, without running PowerShell scripts.

The setup window remains responsive while work runs in a hidden child process.
Interrupted copies resume. Configuration retries retain partial output in the
owned lab's `installer-recovery` folder; fix retries are hash-checked and
idempotent. Existing unrelated destination folders are rejected. Closing the
window during an active install is blocked so the copy is not accidentally
abandoned. Downloads interrupted by loss of connection are reattempted on retry.
They are not resumed partway through an archive.

Failures leave a readable status and **Open setup log** button. Logs are stored
under `%LOCALAPPDATA%/LoreRimLAN/Logs`. The large copy also has
`LoreRim-copy.log` beside the lab. These logs are local; no telemetry is uploaded.

## Validation

- All 46 Python tests pass, including archive traversal/corruption rejection,
  original-save exclusion, physical copy retry, recovery retention, failure
  gates and all-fixes-before-shortcuts ordering.
- The packaged runtime passed read-only preflight against the host's original
  LoreRim 5.0.4.8 / Skyrim 1.6.1170 installation (3,490 original plugins).
- Both automatic downloads passed their pinned SHA256 checks using the packaged
  runtime, without an installed Python or pip dependency.
- A small independent fixture completed the real copy, STR configuration,
  all six actual fixes, verification and native shortcut creation twice. Original
  fixture native files retained their hashes. This fixture used synthetic plugin
  data, a private fixture baseline and a relaxed test-only path limit; it did
  not launch a game or touch live game files.
- The Windows wizard was visually checked. Desktop shortcut creation was tested
  in an isolated temporary desktop folder.

A full-size installation on the second computer and two-client gameplay remain
to be tested. The earlier host lab did load a character and connect locally with
all 3,492 plugins and server ModPolicy enabled.

## Build

With the tested locally built adapter available, on Windows:

```powershell
python installer/build_installer.py --output build-release --adapter path/to/BSAMemoryMap.dll
```

The output folder must be new. The builder uses the Windows .NET Framework C#
compiler, downloads the official Python embed archive, verifies its pinned hash,
retains license notices and generates a checked ZIP plus SHA256 file. The Python
archive digest also matches the message digest in Python.org's published
Sigstore bundle. No claim of independent certificate verification is made.

Download sources:
[Python embed](https://www.python.org/downloads/release/python-31210/),
[STR 1.8.3](https://github.com/tiltedphoques/TiltedEvolution/releases/tag/v1.8.3),
[JContainers 4.2.13.1](https://github.com/ryobg/JContainers/releases/tag/v4.2.13.1).
