# JContainers Lua initialization crash

The October 20 22:53:32 lab crash occurred in JContainers 4.2.9 at RVA
`0xFAD65`, reading `[rcx+8]` with `rcx=0`. The pending Papyrus expression was
`return msm.returnSkillTreeObject(jobject)`.

Disassembly of the installed DLL shows the context constructor calling
`luaL_newstate` at `0xFF100`, storing its null return, then immediately calling
`luaL_openlibs` at `0x100120`. That function calls `lua_pushcclosure` at
`0xFAD50`, producing the observed null dereference. The skill script has not
started executing at this point. This is interpreter allocation failure;
ordinary available system RAM does not rule out a constrained address range.

The author's [4.2.13 release](https://github.com/ryobg/JContainers/releases/tag/v4.2.13)
adds LuaJIT memory support through `msvcbuild.bat gc64 static`. The subsequent
[4.2.13.1 release](https://github.com/ryobg/JContainers/releases/tag/v4.2.13.1)
contains that fix and API additions. Its `SKSEPlugin_Version` compatible-runtime
array includes `0x01064920` (Skyrim 1.6.1170), matching this lab. This update
does not remove JContainers or the custom skills menu.

## Validation

The official DLLs expose `JC_runTests`. Running the author's
`fixture.Lua_evalLua` and `fixture.Lua_launch_all_lua_tests`:

| DLL | Normal process | Free addresses below 2 GiB reserved |
| --- | --- | --- |
| Original 4.2.9 | Both pass | Both fail with SEH `0xC0000005` |
| Updated 4.2.13.1 | Covered by constrained test | Both pass |

The controlled subprocess reserves about 2 GiB of address space without
committing RAM. It reproduces the old allocator's failure class, not the exact
game's full memory layout. The hash-pinned runner is
`native/test_jcontainers_memory.py`; pass a DLL path and `--reserve-low`.
The author's Lua arithmetic, container operations, module loading and Lua test
suite execute in the updated DLL. Installation, idempotent reapplication,
rollback and reinstallation were also exercised in the closed lab.

## Install or restore

With game clients closed, run:

```powershell
python jcontainers_update.py L:/LoreRim
python jcontainers_update.py L:/LoreRim --restore
```

The installer requires the isolated lab marker, rejects overlapping original
installations and linked files, verifies the official archive and all 35
release files, and backs up all 18 changed files outside the mod folder before
replacing them. Existing custom Lua modules and MO2 metadata are retained.
No upstream DLL or script payload is redistributed by this repository.

| Item | SHA256 |
| --- | --- |
| Official 4.2.13.1 archive | `2edd555821e70d94784c79b9a80a34d235f682d4d69f956f28e0411fd43a020a` |
| Original DLL | `3fcd32150c68f1691fe225a76f44911d35cfd0211257190484d1be790de23dac` |
| Updated DLL | `7fe27fccabf99d1e645ee79a1348eb54f0d72097179eb75511afd930ba3b6976` |

The original G: installation retains the original DLL hash. The local full
crash log is preserved separately and is not uploaded. The restarted client reports JContainers64 4.2.13.1 loaded correctly in SKSE.
Character loading and an accepted multiplayer connection remain unverified.
