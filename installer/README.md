# Fast guided installer (0.3)

[Download the installer ZIP](https://github.com/Dr-Dev-Ai/lorerim-lan-lab/releases/download/v0.3.0-experimental/LoreRim-Together-Installer.zip).
Extract it and open **Install LoreRim Together.exe**. The window title includes
**(Fast)** so you can distinguish it from the earlier full-copy installer.

Choose your existing matching LoreRim folder and keep the multiplayer setup
folder on the **same drive**. Setup reuses large textures, meshes, animations,
audio and archives through hard links. It does not duplicate those asset bytes.
Programs, scripts, plugin records, settings, metadata, caches and generated
output remain private physical files. Known writable locations such as overwrite,
Root overlays, tools and screenshot/cache folders are excluded from asset sharing.

The source and lab must be separate folders. Shared assets require a local
filesystem that supports hard links on the same volume. Unsupported destinations
fail with an explanation; the installer never silently falls back to copying the
whole game. The space check counts private file bytes, link metadata and 3 GiB
for downloads, staging and backups. It still scans all source filenames and
creates directory entries, so it is not instant.

## Existing installations

An interrupted 0.2 full copy on the same drive is recognized using its existing
state/marker files. Already copied asset entries are replaced atomically by
links to the source assets; private files are copied independently. This can
reclaim already duplicated asset storage. Completed 0.2 physical copies are
reused as-is; this version does not rewrite completed installations simply to
change their storage layout. Cross-drive partial copies require a new destination
on the source drive. Nothing deletes the old cross-drive copy automatically.

Stop the old installer and its copy process before starting the new one. The
preflight refuses to proceed while robocopy is running. A new setup can be
retried after an interruption. Configuration recovery retains partial output,
and all six fixes remain hash-checked and idempotent.

## Shared-asset tradeoff

The installer does not patch any original source bytes. Its fixes operate on
private DLLs, scripts and settings. Hard-linked assets reference the same disk
bytes: editing an asset through either path affects both. Keep both setups on
the same modpack version, and do not update mods or run asset-generation tools
through the LAN workspace. The lab's MO2 exposes only the multiplayer launcher.
This is not an independent backup of the source assets.

## Included and downloaded components

The portable ZIP includes the licensed official Python runtime and our tested
BSA adapter. It downloads pinned official STR 1.8.3 and JContainers 4.2.13.1
archives, configures the isolated profile, stages dependencies, applies every
fix and creates play/help shortcuts. No Python installation, pip, administrator
access, terminal commands or PowerShell policy changes are needed.

No game or original mod binaries are bundled. Requires the same installed
LoreRim 5.0.4.8 / Skyrim 1.6.1170 as the host. Desktop shortcuts are created
through the Windows COM API. Logs remain local under
`%LOCALAPPDATA%/LoreRimLAN/Logs`, with `LoreRim-link-report.json` beside the lab.

## Validation

All 52 automated tests pass. New tests verify asset file identity, independent
DLL/script/settings writes, conversion of a partially copied asset, exclusion
of large shared bytes from the space estimate, rejection of unsupported links
without fallback, and refusal to overwrite an unrelated shared destination file.

A small isolated integration fixture resumed an interrupted 0.2 copy, linked
128 MiB of synthetic assets, applied all six actual fixes to private files,
verified unchanged original DLL bytes, created native shortcuts and completed
an idempotent retry. Only about 40 MiB of fixture programs/scripts/settings was
copied. The fixture used a private plugin baseline and relaxed test-only path
limit; it did not launch a game or modify live installs.

The host's earlier physical lab loaded a character and connected locally with
3,492 mods. Full-size linked-asset setup on the second computer and two-client
gameplay still need validation. Creating links is not a gameplay certification.

## Build

On Windows with the tested adapter:

```powershell
python installer/build_installer.py --output build-release --adapter path/to/BSAMemoryMap.dll
```

The output folder must be new. The builder compiles the Windows frontend,
verifies the pinned Python embed archive, retains Python/MinHook license notices,
and writes a verified ZIP, per-file manifest and SHA256 checksum.

References: [Windows hard links](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions),
[Python](https://www.python.org/downloads/release/python-31210/),
[STR](https://github.com/tiltedphoques/TiltedEvolution/releases/tag/v1.8.3),
[JContainers](https://github.com/ryobg/JContainers/releases/tag/v4.2.13.1).
