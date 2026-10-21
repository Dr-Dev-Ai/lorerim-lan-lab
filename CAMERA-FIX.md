# Experimental camera scanner correction

The installed Improved Alternate Conversation Camera AE 1.2.0.0 scanner excludes
STR's RWX pages. `camera_fix.py` corrects the verified protection predicate in
14 compiled scanner variants. Each immediate changes from `0x20` to `0x60` (RX
or RWX). MEM_COMMIT tests, guard-page rejection, search algorithms, camera hooks
and feature settings are unchanged. No game/mod DLL is distributed.

## Apply or restore

Close all Skyrim clients. Use only a physically isolated, marked lab:

```powershell
python camera_fix.py 'D:\LoreRim-LAN\LoreRim'
python camera_fix.py 'D:\LoreRim-LAN\LoreRim' --restore
```

The installer requires the exact original SHA256
`fd09d76ec7a3288787fbf3f0c1bfba69b43c12e73f48f3b7a146e4986430acb7`.
It checks instruction bytes at the listed file offsets; it never scans for and
replaces arbitrary constants. A different version is rejected. It refuses an
original/overlapping installation, linked DLLs, changed DLLs after backup, and
running game clients. The original is retained in
`camera-fix-backup/AlternateConversationCamera.dll.original`. Keep this backup.
Installation uses a verified temporary file and atomic replacement. Reapplying
is idempotent; restore refuses to overwrite an unrecognized user change.

Patched SHA256:
`fabdcc959dd64c43861e58ca75d6b95feb0315d7a9d4675ad40c1d4797cbb53f`.

Do not apply automatically to new setups or other camera builds. Both LAN PCs
must use identical DLLs and regenerate manifests after installation.

## Validation on 2026-10-20

1. A one-byte correction at file offset `0x15811` cleared the original FOV
   pattern error. Startup reached the next pattern, `8b4758894764`, which also
   occurred exactly once on a committed RWX page (RVA 9339038) with no probe read
   errors. This intermediate build was restored before the complete correction.
2. Disassembly of each VirtualQuery scanner established the same MEM_COMMIT,
   protection and guard checks. The fourteen changed file offsets are:
   `112D`, `15E1`, `1AC1`, `1FC5`, `24D1`, `29B1`, `15811`, `15D05`,
   `161FD`, `165E1`, `18BF1`, `19A35`, `19F31`, `1B951` (hex).
3. Byte comparison verified exactly fourteen changed bytes; the original
   installation still matched the original SHA256.
4. Live startup with the full correction logged:
   `plugin AlternateConversationCamera.dll (00000001 Improved Alternate Conversation Camera 00000079) loaded correctly (handle 9)`.
   Loading continued through subsequent plugins without the previous camera dialog.
5. All 22 automated tests passed, including exact change, idempotence, rollback,
   unknown binary, changed user file, running game and hardlink refusal tests.

This establishes correction of the observed scanner startup failure. It is not
certification of dialogue behavior, FOV restoration, SmoothCam integration,
letterboxing, gameplay or multiplayer synchronization. Those still require
actual in-game acceptance testing. This is a local binary correction, not a
recompiled camera source build.

## Next observed startup blocker

This launch subsequently stopped at Don't send me there again (dosemetha):
`main.cpp(110): Failed to hook GetLocationsCandidates`. The dialog and log agree.
Installed mod metadata says 1.1.1.0; its own log reports v1-1-0-0. DLL SHA256:
`e64dc70941dbe5cfa97b3198a9a4ec376f50cfaf9de8e73bbec7d372cb0a44a7`.
This is a separate unresolved hook failure; its cause has not been established.
No dosemetha patch or disabling was performed. The game did not reach the menu.
