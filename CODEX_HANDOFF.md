# Codex handoff — LoreRim multiplayer, October 23, 2026

## Start here

The user wants the remaining LoreRim multiplayer issues fixed, with working sleep/time/needs and co-op campaign persistence. **The latest v0.5 native build failed real startup on BOTH PCs and was rolled back. It is NOT installed or ready to apply.** Do not confuse passing build/protocol tests with gameplay acceptance.

Latest immediate issue: sleeping while connected does not advance time, does not reliably restore exhaustion, and magicka does not regenerate. The user manually ran \`set Survival_ExhaustionNeedValue to 0\`. The subsequent healthy-looking Active Effects list is not evidence that sleeping worked.

Read-only console output on the host character **Ze'Mofed** was visually verified:
- \`player.getavinfo magickarate\`: current/computed base **1.05**, Temp 0, Perm 0, Damage 0.
- \`player.getavinfo magicka\`: current **70**, computed/reference base **100**, Temp 0, **Perm -30**, Damage 0.
- \`player.getavinfo magickaratemult\`: current **0**, computed base **100**, Temp 0, **Perm -100**, Damage 0.
- The zero multiplier explains blocked regeneration. The originating mod/condition is **not confirmed**; "permanent" is an actor-value modifier category, not proof of irreversible corruption.
- No forceav/modav repair has been applied. Do not blindly add 100 or reset every stat.
- Earlier alcohol hypothesis is unconfirmed for the current effects. Current DVSMP log showed Hot Beef Stew restoring thirst to zero.
- Loose-script scan examined 14,180 winning PSC/PEX files. The only \`magickaratemult\` match was Rite of Arcana's ROA_QuestScript; private decompilation showed READS of that AV, not evidence it applies this modifier. Do not blame Rite of Arcana from that match.
- Official Survival Mode Improved source does implement maximum-magicka penalties through permanent AV deltas with separate bookkeeping. That supports investigating the -30, but does not identify the -100 regeneration modifier.
- Do not repeat unreliable background keyboard injection. It failed to enter console queries and opened menus; the user successfully entered the three read-only commands manually. Read game captures without changing input.

## Verified current installed state

Both games were launched successfully using the restored pre-v0.5 clients. The previous matching server was restored and verified listening on UDP 10578. Games may have changed state since; recheck before stopping anything.

Host Desktop Commander device: DESKTOP-J6TETDJ (discover its current ID with list_devices).
Partner device: Terra (discover its current ID with list_devices).

Host:
- Game/MO2: \`L:\LoreRim\`
- Active profile: \`L:\LoreRim\profiles\LoreRim LAN Test\`
- Profile saves: \`saves\` (MO2 virtualizes \`__MO_Saves\`)
- Client: \`L:\LoreRim\mods\LoreRim LAN - Skyrim Together 1.8.3 (1170)\SkyrimTogetherReborn\`
- Server: \`L:\server\`
- Main source/work root: \`C:\Users\brand\Documents\Codex\2026-10-20\lorerim-lan-lab-development\work\`
- Full native worktree: \`<work root>\lorerim-native-staging\`
- This helper repo: \`<work root>\lorerim-lan-lab\`
- Earlier full original source: \`C:\Users\brand\Documents\Codex\2026-10-20\build-a-working-two-player-lan\work\TiltedEvolution\`
- L: is a SUBST to that earlier task's \`work\isolated\` directory; do not overwrite a real drive mapping.

Partner's ACTIVE installation is on **F:**, verified through her desktop shortcut and MO2 gamePath. An old D: copy also exists; do not update/delete the wrong copy.
- \`F:\LoreRim-LAN\LoreRim\`
- Profile \`profiles\LoreRim LAN Test\`
- Windows account \`C:\Users\oldka\`
- Her before-update backups: \`F:\LoreRim-LAN\update-backups\v05-20261023-202241\`
- Her deployment/rollback record: \`F:\LoreRim-LAN\updates\v05\APPLIED.json\`

Restored matching binary hashes:
- SkyrimTogether.exe: B4316ADE189C8BD988A747EAD72953232138AC34B39D20B1CBB6360F2627E49E
- EarlyLoad.dll: CB9C6118494F05F174C04EFA2FCC9B55482BA068A9F6195931157185B889DB50
- Server runner: BBBAC51C5E34BA4CF890E61BDA33C425FE4790DE75F92E4F4561AB02CF072E18
- STServer.dll: ED61BA98478C66C4CA39BA602B7B2BBE7A8EF8AF94A3A364A7AE8A8EFD1F89E5
- The server DLL has the earlier exact binary health-broadcast guard; see SERVER-HEALTH-AND-REST-STATUS.md.
- Host pre-update backup \`<helper>\applied-update-backups\v05-20261023-200310\` contains four binaries, original server config/modlist and all 37 profile save files. Partner backup contains 27 save files.
- Rollback restored both pre-update mod lists; the v0.5 patch mod remains on disk but is inactive. Saves were NOT restored, edited or overwritten.
- Campaign guard is disabled. Both native identities/enrollment remain pending. No managed paired campaign checkpoint with real player saves exists.

Before rollback, both profiles had 3412 enabled plugins with identical normalized order. That comparison does not certify every plugin/BSA/DLL file.

## v0.5 failure: highest-priority engineering blocker

Source build identity \`lorerim-campaign-bridge-v0.5-staged\`.

1. Initial native launcher mistakenly allowed only 1.7.104.0. Installed game is 1.6.1170.0 on both PCs. A source hotfix added 1170 alongside 1.7.104 and fixed BUILD_COMMIT display dropping its first character.
2. After that check was fixed, both clients crashed during Papyrus VM initialization, before loading a save.
3. Host CrashLogger:
   - \`C:\Users\brand\OneDrive\Documents\My Games\Skyrim Special Edition\SKSE\crash-2026-10-23-20-31-03.log\`
   - Process 644; uptime ~119 seconds.
   - EXCEPTION_ACCESS_VIOLATION at **0x180633CE1**, instruction \`call [rax+0x48]\`; RAX 0x141AA0E20.
   - Next stack address 0x1807512C0, then skse64_1_6_1170.dll+E4AE and Skyrim VMInitThread.
   - Offline PDB lookup resolved these addresses only to \`game_seg +0x532ce1\` / \`game_seg +0x6502c0\`; do not claim those are identified custom C++ functions.
   - Partner also produced a new crash log at 20:31:25.
4. Root cause is **unverified**. Inspect Papyrus registration, ABI/layout and compatibility with the 1170 runtime. Do not assume merely adding a version string makes a newer upstream branch safe.
5. Relevant staged code: \`Code/client/Games/Misc/BSScript.cpp\`, \`Games/Skyrim/Misc/BSScript.{h,cpp}\`, new RestExchange/NextEquipmentActor/CampaignFollower/NextCampaignFollower registrations.
6. Current experimental source is retained, with an explicit DO-NOT-INSTALL marker in the candidate folder. The matching runtime used for successful play is the old binary set above.

## Source and build locations

This branch contains:
- \`native-staging/overlay/\`: source-only modified/new files relative to upstream; excludes compiled files and private decompiled third-party scripts.
- \`native-staging/lorerim-v05.patch\`: corresponding source-only patch.
- \`native-staging/README.md\`: exact upstream base, full development commit and build/reconstruction instructions.
- \`campaign-manager-staging/LoreRim-Campaign-Manager/campaign_manager/\`: latest Python manager, protocol/storage tests and status.
- Existing helper diagnostics and exact binary-repair tools.

The full Windows worktree is more complete than an overlay and remains the authoritative place to inspect SDK dependencies/private build inputs. Native head at handoff: e1cd251 (after the startup failure status commit). Earlier commits: 4126892 (coordinated checkpoints), 3266aac (1170 version gate). Native upstream base before task changes: 5a72cdc. Do NOT push to the native worktree's origin, which is tiltedphoques/TiltedEvolution.

Private scripts NOT published: generated extended SFF DialogueFollowerScript, decompiled vanilla dependencies, StaticSkillLevelingQuestScript and rental override sources. Their staged local versions are under \`<native tree>\lab\LoreRimLANRest\source\` and the private compiler directories below. Review local originals and create minimal source-preserving patchers rather than publishing decompiled scripts.

Build tools:
- \`<work root>\build-tools\git\cmd\git.exe\`
- \`<work root>\build-tools\xmake\xmake\xmake.exe\` (3.x)
- VS2022 tools under \`C:\CodexBuildTools\`
- Python 3.12.10 on host
- Outputs: \`<native tree>\build\windows\x64\releasedbg\`
- Private flat SKSE SDK PluginAPI.h: \`<work root>\build-tools\reference-skse\`
- Papyrus compiler: \`build-tools\papyrus-compiler\PapyrusCompiler.exe\`
- Champollion: \`build-tools\champollion\Champollion.exe\`
- Dependency sources: \`build-tools\private-papyrus\source\`
- SFF generated source/PEX: \`build-tools\campaign-followers\staged-v031\`
- Parking script PEXs: \`build-tools\campaign-followers\parking-v04\`
- Official SMI source was cloned read-only to \`build-tools\reference-survival-mode\`; check its version against the installed SMI 1.5.2 before relying on implementation details.
- Private ROA diagnosis source: \`build-tools\private-papyrus\rite-of-arcana-diagnosis\ROA_QuestScript.psc\`

Build ONE xmake target per invocation; nonexistent target can misleadingly report success. Check actual binaries. Targets:
\`SkyrimServerRunner\`, \`SkyrimImmersiveLauncher\`, \`TPTests\`, \`CampaignBridgeProbe\`, \`LoreRimCampaignCosave\`, \`CampaignCosaveProbe\`.

Configuration regenerates BuildInfo; stamp AFTER \`xmake f -m releasedbg -y\`. Client, server DLL and server runner must have the same BUILD_COMMIT. Do not ship a newly linked DLL next to an older runner.

Read upstream AGENTS.md before engine work. It requires binary evidence for unverified engine behavior and no gameplay unit tests without asking. User previously authorized experimental source-only engine development without IDA/Ghidra; this is not proof guesses are correct. Pure protocol/data/serialization tests are permitted. Do not spawn subagents unless separately authorized.

## What was implemented, with limits

- Python transactional store: immutable paired save backups, strict profile/runtime fingerprints, journaled/idempotent ownership/transfers, stable native character/epoch/checkpoint binding, recovery-copy domain rewind.
- Loopback API on 127.0.0.1:10579 with credential-scoped operations. Never log/publish credentials, saves, database or native upload directories.
- Native SKSE co-save identity companion and admission barriers: exact enrolled ESS/SKSE hashes, character, epoch and branch head; defer gameplay/party publication until admission; detect supported offline mutations.
- Connection presence leases and durable world-dirty marker batching.
- Coordinated paired save protocol: both peers pause/drain pending mutations, check profiles, seal one revision, request saves, stream ordered hash-verified chunks; atomically commit both pairs and ledger; retain previous head on abort.
- Server time freezes during checkpoint sealing; this is distinct from fixing sleep-time skipping.
- Standard SFF ownership guards, alias reporting and native AI ownership/parking policies, epoch/sequence checked; no cloning/resurrection.
- Experimental shared-rest packets, server clock/date advancement, timer bookkeeping, team exhaustion/rest benefits, conditional own-player skill menu, rental fallback and equipment refresh.
- Drop claims at most once within the session; signed counts and equipment metadata improvements.
- Source object-animation GameId/range/leader replay guards; incomplete prop visibility/late-entry synchronization.

These implementations are staged source, not working installed features.

Tests before actual startup failure:
- Native protocol: 225 assertions / 13 cases.
- Python: 63 tests pass Linux; Windows 62 pass + 1 symlink privilege skip.
- Companion DLL mock-SKSE lifecycle/serialization/ABI probe passes.
- Real native network/API admission: 10 cases pass, including wrong save/character/epoch and pre-admission fence.
- Two synthetic native peers upload four verified files; paired checkpoint commits and both receive resume.
- SFF/parking scripts compiled with zero errors/warnings privately.
- **None of those passes overrules the real 1170 startup failures.**

## Remaining required work

1. Diagnose magicka modifier origin and implement a narrow, justified repair if stale state is confirmed. Do not force actor values to hide the problem.
2. Fix 1170 native startup safely, then isolate and test the sleep change before combining all campaign features.
3. Complete shared sleep/time and Survival Mode Improved exhaustion reconciliation. Resetting a need global alone is not equivalent to normal sleep bookkeeping. Both characters need appropriate benefits and their own available-point menus.
4. Per-topic dialogue permissions: fixed campaign leader for quest fragments; ordinary services/rentals available sequentially; follower recruiter ownership independent of who simulates AI.
5. Durable per-item identities/receipts across supported inventory/storage/vendor/follower/ground paths. A database artifact journal alone is NOT one-of-a-kind enforcement.
6. Durable ground-drop reconciliation or explicit paired rollback boundary. Current staged checkpoint rejects active shared ground drops.
7. Sawmill enabled/disabled props and late-entry synchronization; correct back equipment; rental regressions; custom follower/hotkey coverage and missed-death reporting.
8. Real two-client gameplay, disconnect/reconnect/restart and crash/recovery acceptance tests.
9. Arbitrary offline quest/world merging remains unsupported. Supported solo imports are not implemented; do not promise automatic merging.

The user prefers completing concrete work and candid short status, not repeated confirmation requests. Applying v0.5 to both PCs was authorized, but it failed and was rolled back. Coordinate any new interruption of their current game; keep verified backups and do not restore old saves over new progress.

## Suggested next Codex task

"Read CODEX_HANDOFF.md. Resume from the current rolled-back working runtime. First investigate the verified MagickaRateMult permanent -100 and Magicka permanent -30 without blanket forceav changes, then fix the native 1170 Papyrus-startup crash. Separate the sleep/time fix into a small verifiable candidate. Preserve both players' saves and the working server, and do not claim build/protocol tests prove gameplay."
