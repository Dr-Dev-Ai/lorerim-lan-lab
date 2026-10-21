# Bestiary title-screen workaround

The guest crash at 2026-10-21 01:54:51 failed at
`DragonbornsBestiary.dll+004D717`, dereferencing a null GFx movie in
`Scaleform::HUDWidget::SetPosition`. Its caller at `+0022A31` is the widget-open
event. This identifies the failing path, not why the movie failed to initialize.

The upstream source examined was
[jpsteel/skyrimbestiary b4a8369](https://github.com/jpsteel/skyrimbestiary/tree/b4a8369be109f42405301c55db947e121236fd6a/src).
`main.cpp` calls HUDWidget::Show unconditionally, including at data load.
`HUDWidget.cpp` dereferences the movie without checking it. The INI toggle alone
gates notification queueing in EventProcessor/PapyrusFunctions; it does not gate
startup widget creation.

The standalone repair changes only the optional HUD behavior:

- Supported DLL SHA256: `06ac689bb7c9324f51ad822e4b1b469fd8cf1e4d7a621e529516522fa66445dd`.
- File offset `0x4CA00` (RVA `0x4D600`, SetPosition): first byte `48` becomes `C3`.
- File offset `0x4CCC0` (RVA `0x4D8C0`, Show): first byte `48` becomes `C3`.
- Both are void, no-argument functions. The early RET precedes the prologue;
  no stack adjustment, register save or object construction has occurred.
- The effective multiplayer-profile `Dragonborns Bestiary.ini` has
  `iEnableWidget=0` to stop both callers from queueing notifications for the
  absent widget. General section, setting shape and changed-file state are checked.

The DLL hash and instruction prefix are checked before any edits. Both original
files are backed up, existing altered backups/targets are refused, DLL overrides
and reparse paths are refused, and atomic replacement preserves shared original
files. Failure during replacement attempts restoration of both current files.
Close the game and MO2 first. Repeat application and byte-exact restoration are
supported. This does not disable the Bestiary plugin, remove scripts or change
plugin ordering. It is not installed automatically by the v0.3.0 main installer.

Build with `python installer/build_bestiary_repair.py <output-directory>`.
The C# source includes a `--self-test <original-DLL>` mode which operates only in
a new temporary fixture. Compile as a console EXE to capture test output.
No original mod binary is distributed.

Validation covers the exact two-byte extent, apply/retry, restoration/retry,
preserving a hard-linked original, changed-settings refusal before DLL mutation,
unknown DLL refusal and UTF-8 BOM preservation. Native entry-point checks execute
the repaired entry bytes in a fresh executable buffer without loading the mod.
**Her title-screen/gameplay test is outstanding.** No claim is made that missing
or broken UI resources have been repaired, or that other crashes are resolved.
