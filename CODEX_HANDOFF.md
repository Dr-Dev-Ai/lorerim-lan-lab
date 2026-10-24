## First multiplayer death check passed — October 24, 00:54

Installed client 2ab06f8d...20a16c5 (native code 54c14cf), host PID16860,
isolated server PID29888/10580 with death mode enabled. User confirmed ordinary
enemy death respawned, remained connected and restored movement. Client log:
respawn began 00:54:16.037, completed 00:54:21.053 and notified server. No save
load or disconnect followed this death. This supersedes the first-death pending
status below. Repeated death and deliberate connected-load fallback are still
pending; two-client respawn visibility has not been tested. Save20 stays backed up.

## Death / save-load guard candidate installed — October 24

User reported death automatically loading a save while the multiplayer session
remained connected. The isolated server on 10580 had bEnableDeathSystem=false;
production on 10578 already had it true and was not changed or restarted.
The isolated LoreRim profile already stops the competing Respawn quests through
its compatibility AutoExec. Only this test server config now enables death mode;
the generic lab generator is unchanged because its baseline handler setup differs.

Native code 54c14cf adds connection-scoped respawn timer cleanup and restores
essential protection if a delayed compatibility handler clears it. Existing
engine accessors and the existing bleedout/respawn path are reused; no new engine
offsets or hooks were introduced. Existing engine behavior remains assumed
without IDA/Ghidra verification. A completed connected save load now closes the
transport instead of revisiting the cell in the stale session. This post-load
fallback does not roll back peers or make older saves consistent with the party.

Client and matching PDB built successfully. Installed client SHA256:
2ab06f8d549e4a9cf8c62603a3c9be0672537727f35fd924f77842cfb20a16c5.
Wire identity remains lorerim-rest-recovery-v0.6; no server binary/protocol change.
Save20 ESS + SKSE, previous client and old test config are hash-verified backups
under the October23 task work/death-load-guard-candidate/before-install.
Rollback manifest preserves the original binaries. Isolated server PID29888
listens on 10580; new host launch requested through MO2 at 00:38.

Runtime acceptance PENDING: load Save20 offline, connect 10580 blank password,
confirm death mode enabled, then test ordinary lethal combat (not console kill).
Expected: bleedout, roughly five-second delay, in-session respawn, no save load,
connection retained, movement restored, repeatable death. Separately verify a
manual connected load disconnects with the HUD explanation. Do not claim either
test passed from compilation/startup alone. Preserve the pretest save.

Earlier dashboard and menu host acceptance remain valid; two-client telemetry,
unpartied sleep, residual magicka regeneration and broader co-op remain open.

# Codex handoff â€” LoreRim multiplayer, October 23, 2026

## Start here

SYNC HEALTH HOST ACCEPTANCE PASSED Oct24: user confirmed panel visible and all
F10modes work; detailsleftopen and visuallyinspected. PID28840 remainslive,
client91bd7741...c8fc47c/nativecode910f468. Observed ping0ms, quality100%/100%,
queue0ms, pendingreliable0bytes, localactors2, remotestreams0, clockestimate+1.1
gameseconds, clientupdate4.8ms, onehistoricalupdategap>250ms. Plausiblelocalserver
measurements; do NOT interpretasproofquest/inventoryagreement. Remoteactor
age/jitter/correction telemetry needssecondclient. Serverprocessingunreported,
quest/inventoryunmeasured, connected-loadwarningnotdeliberatelyinduced.
PrivateacceptanceJSON inOctober23task work/sync-health-candidate/acceptance.json.
No moreinstall/relaunch needed. Do not terminateunsavedhost. LatestbackupSave18.
Unpartiedsleep, residualmagickaregen penalty andbroadco-opacceptanceremainopen.


SYNC HEALTH CURRENT: PID28840 reached main menu (visuallyverified), service-ready
log00:07:09.080, no new crash observed. One automatedContinueclick had no visible
effect; do NOT repeat blind inputs. Asyncpromptpending: user loadlatestoffline,
join10580blankpassword, testF10details/hidden/compact andleavedetailsopen.
Native910f468 / client91bd7741...c8fc47c installed. Save18 ESS+SKSE and prior
menuworkingclient backedup/hashverified. Bothserversunchanged. No runtime panel
visibility/metric/hotkey acceptance yet. Publichelper sourcea9fa599 preserves
146-filepatchcheckedagainstbase; do not mistake startup for dashboard validation.


SYNC HEALTH RELAUNCHED PID28840 at00:07:06 Oct24. Startup log confirms service
ready00:07:09.080 and menu opcode checks pass. MO2unlock/Runalreadydone. Await
manual latestsaveOFFLINEload then10580connect andF10 modes/detailsopen response.
Do not relaunch/replace again while this session is live. Currentclient91bd7741,
configMode1, F10, X24/Y150, scale125. Save18/menuclient backupsverified.


SYNC HEALTH INSTALLED: user reported saved/closed. deploy_sync_health.py copied
latestSave18 ESS+SKSE and accepted menu executable into work/sync-health-candidate/
before-install with hash checks, installed91bd7741...c8fc47c and optionalINI under
hostoverwrite/SKSE/Plugins. Existing original rollback preserved and manifest
candidate updated. Host executable not yet launched at this note; MO2orphanlock
unlocked, currentlyrefreshing. Both servers untouched. Need Run13 whenenabled,
then loadsaveOFFLINE, connect10580 blankpassword and checkF10panel modes.


LATEST SYNC HEALTH WORK, October24: user requested the in-game dashboard.
Native910f468 implements a read-only SyncHealthService, default compact while
connected; F10 cycles detailed/off/compact. INI template/docs inlab/sync_health.
Network quality/queue, per-actor age/jitter/buffer/corrections, update gaps and
estimated time-of-day difference. No new protocol/server changes. Server CPU/
processing time and quest/inventory agreement explicitly unmeasured. Uses
UpdateEvent sampling and mutex-protected render snapshots, bounded history.
Connected load warning records risk without changing load/disconnect behavior:
normal DiscoveryService currently only revisits the cell, no full server rollback.
Disconnect BEFORE loading and reconnect using an agreed save; the earlier Save16
reload check proved crash/save functionality, NOT multiplayer state agreement.
Buildpassed. Candidate91bd7741...c8fc47c + matchingPDB staged inOctober23task
work/sync-health-candidate; NOT installed yet. Host10760 still live. Asyncrequest
pending: user must save/quit before deploy_sync_health.py can back up/install.
Do not terminate unsaved progress. Test server31628 and production24400 unchanged.
After installing: launchthroughMO2, user loadsaveOFFLINEthenconnect10580, inspect
compact andF10details/off, camera/menuregression. Unavailable metrics muststayN/A.


LATEST HOST MENU ACCEPTANCE (supersedes pending-menu notes below):
Source package synchronized through18db4ab (acceptance docs); installed binary
contains codeee529b2. New candidate/acceptance documentation does not change binaries.

### Host menu acceptance completed, 23:35 local

Installed menu candidate c77ffed2...96248f (native ee529b2) passed:
- Map held open: five read-only samples across 8.003 real seconds; UI pause
  count0 and VM inactive0 throughout; game hour14.2464066 ->14.2911301,
  matching timescale20 (about161 game seconds in8 real seconds).
- Journal held open: two samples with on-stack flagsF4C, pause count0 and VM
  inactive0; game hour14.6174488 ->14.6285286 in2.001 real seconds.
- New manual Save16 queued23:34:37.100; engine returned success23:34:37.965;
  finished loading23:34:54.232. User confirmed new save/reload succeeded.
- User confirmed first/third-person map open/close, local-map toggle, and
  movement/camera/sound afterward were all normal.

Latest progress is Save16 (Tamriel000428,20261024063437); ESS+SKSE copied and
hash-verified under October23task work/menu-fix-candidate/accepted-new-save.
Earlier Save15 backup remains. Live host10760 was not terminated or reverted.
Evidence JSON and raw samples remain private under menu-fix-candidate.
These are host checks. Arbitrary custom menus, overwrite/quicksave paths,
paired-checkpoint regression and two-client synchronization remain untested.
Intentional Loading/Main/Fader, active sleep/wait and paired-checkpoint pauses
remain; ordinary connected menus use the expanded unpause policy.
Unpartied sleep and the remaining magicka regeneration penalty are separate
unresolved work. Do not mark all co-op acceptance complete.


LATEST RUNTIME: menu candidate PID10760 loaded Save15 and connected to isolated
10580 server at23:30:57. Journal Menu opened at23:31:12 and23:31:36; both logged
flags F2D->F0C on main thread31812. Game remained running, VM inactive0, pause
count0 between menus. These are hook/connection checks, not full acceptance.
Async question pending: leave Map open and report ready. Need sample clock and
pause counter while Map is held, first/third-person and local/world-map checks,
then create a NEW manual save and reload it (do not overwrite backup Save15).
No queued/completed manual-save messages yet. Never terminate this live session
with unsaved progress. PR source sync9ec187a pushed; title/body updated, stilldraft.


SOURCE PACKAGE SYNC: native-staging/overlay, source-only patch and manifest now
match native ee529b22a684aef20268061b44afcddb14c3ea5a. The 141-file patch applies
cleanly to exact upstream base. Compiled/private third-party scripts remain
excluded. This supersedes older notes saying overlay is still v0.5.


LATEST MENU CANDIDATE (supersedes older deployment notes):

### Connected menus candidate, after pickup acceptance

User confirmed fresh bread drop/pickup works. Test server logged successful
claims for drops 532575944705 and 532575944706 with replication disabled.
This establishes repeated single-item pickup, not stacks/two-client contention.

User then reported Map and Journal/Escape pause while connected. Candidate
unpauses ordinary connected menus before stack insertion (including custom
menus); keeps Loading/Main/Fader, sleep/wait transactions and explicit paired
checkpoint pauses. Journal manual saves are deferred through the engine save
event queue; UI processing moves from its worker job to after MainLoop returns.
Offline menu flags retain normal pause behavior, but UI scheduling also changes
offline on 1170. A pre-existing journal is paused/unpaused around checkpoints
with the UI pause counter updated. First-person map player update accepts a
hidden node while connected; local-map updates cannot restore frozen rendering.
No new plugin, protocol change, server restart, or Papyrus deployment.

Reference: https://github.com/Vermunds/SkyrimSoulsRE at
2cbd7d5a0e2a6a04381b4076ac73e8d51332fe32 (GPL-3.0), especially SaveHandler,
MenuProcessing and MapMenuEx. Adapted behavior, not a complete Skyrim Souls port.

1170 Capstone evidence from game memory dump (NO IDA/Ghidra MCP verification):
- 35727 -> 14060FD40 save function; all four calls/tail branch validated at
  22940+C4, 52923+2B, 35533+3E/+60, same target.
- 35772+5D5 cmp ECX,F0000800, original case +5E1, continuation +72A;
  custom F0004000 calls queued save; unrelated events skip it.
- 39042+B JNE25 skips UI job body, retaining original completion signal.
- 36581+7A FF9080030000 calls player vtable+380 then tests RAX. Existing
  TESObjectREFR::GetNiNode matches that slot. Hidden node exception only at site.
- 53112+9D writes EAX to flags+1C; wrapper removes background freeze afterward.
- 36564+D0 reads UI+160, then Main+16 at +E3, determining paused vs unpaused path;
  main joins work before returning. Post-return scheduling is an experimental
  assumption; unlike reference's hardcoded +AF1, it uses existing MainLoop hook.
All added patch sites check opcodes/branch targets before installation; mismatch
retains old menu allowlist. Thread correctness, camera/audio/weather rendering,
manual save/load and two-client progression still require gameplay testing.
Native compile passes; no new gameplay unit tests written.

Client c77ffed282dcfed607b9a47a6c6c118364761b8810f404c93a0463157a96248f
installed after user saved/closed; Save15 ESS+SKSE and prior working pickup client
hash-verified in October23 task work/menu-fix-candidate/before-install. Matching
candidate PDB retained in staging. Rollback manifest updated, original backups
preserved. Test server31628/10580 and production24400/10578 untouched.
Runtime startup and connected menu/save acceptance PENDING.


### Local continuation after the 22:06:55 host crash

LATEST DEPLOYMENT supersedes staged-only drop notes below: user recovered bread
after disconnecting, saved and closed. New Save14 pair at22:55:25 backed up and
hash-verified in October23task work/drop-fix-candidate/before-install. Native
42d0eb5 client cf712af5...6fabe0 now INSTALLED; test STServer55b0684d...34c97c
and matching runner installed, test server restarted as PID31628/10580 (logs
work/sleep-test-v06/server-dropfix-output.log). Production24400/10578 unchanged.
Rollback manifest updated preserving original working binaries. Host launched
PID29096 at22:57:23, still loading at last check. User asked: loadSave14,connect
10580 blankpassword,note breadcount,dropone,pickonce,check originalcount. Await
reply/log acceptance. Do not claim pickupfixed from build alone. No need to
repeat backup/deploy/restart already done. Native public overlay still needs
sync from fulltree and PRupdate when appropriate; helper native-staging still
oldv05source. Native upstream must NEVER be pushed; helper PRbranch allowed.

LATEST DROP BUG: user dropped bread, repeated pickup feedback but no inventory
credit. Current server has bEnableItemDrops=false. Source mismatch: client
tracks originals and blocks pickup pending a claim, but server only recorded
drops when remote replication was enabled. Native commit `42d0eb5` always
records drops, stores Replicated per drop, sends picker claim receipt and
ordinary inventory delta to peers without replicas; adds diagnostics.
Client/server builds pass, existing225/13 protocol tests pass (not pickup
acceptance). Compiled candidate is PREPARED, NOT INSTALLED, October23 task
work/drop-fix-candidate/manifest.json. Client cf712af5...6fabe0,
STServer.dll55b0684d...34c97c. Installed host still21b025d8...8f95e34;
test server PID30996 still old running DLL; production24400 untouched.
User was asked to disconnect, try original bread (tracking clears on disconnect
without deleting original), save and quit, then report recovered/stuck/keepopen.
Await that reply; do not terminate host with new unsaved progress. After exit:
back up current save pair, deploy prepared client and matching test-server
binaries, restart ONLY isolated10580server, update rollback candidate manifest,
launch and test fresh drop/pickup plus stacks before claiming success.
Latest native recovery doc records full hashes, logic and limitations.

LATEST SLEEP RESULT: user confirmed it works in a party but not outside one.
Client/server PartyRest session1 completed 8h at 22:46:43; server logged clock
advancement accepted. One-player party only. Post-rest snapshot private
October23 task work/sleep-test-v06/effects-after-party-sleep.json: Weary0x833
absent, Variable03 candidate34->3, but regen multiplier permanent -100 persists.
Do not claim magicka fully repaired. Beforeparty sleep produced no Begin:
current script/client/server require party leader/membership while connected
calendar hook freezes normal game clock. Unpartied sleep remains unsupported
and unresolved. No native change made yet for that condition. Host is still
running and user has progressed/levelled; preserve current progress before
any future restart. No new save has been requested or restored by Codex.

LATEST LIVE CHECK: user loaded same save on PID 30780. Read-only checks passed
11 quest objectives, 21 tints, skills XP330, difficulty1, initialized animation
strings. Captures: October 23 task work/sleep-test-v06/player-fields-loaded.json,
player-extension-loaded.json, effects-before-connect.json. User was asked to
connect 127.0.0.1:10580 with empty password and wait without sleeping. Logs now
show accepted connection at 22:42:29, player assignment Request14/cookie0 and
continued actor sync with no new crash. Await user stability report. Party
creation/rest NOT yet tested. Preconnect Weary effect still -200; AV candidate
Variable03=34, needs console corroboration before attributing max-magicka loss.

LATEST after 22:33:48 CONNECTION CRASH: password clearing succeeded; test
server accepted 3492 mods, then client crashed at 0x1806DF750 in
CharacterService::RequestServerAssignment+0x4E0 reading objectives from wrong
player offset +0x590 (RBX=0xB). Native commit `d61163a` adds 1170-aware
accessors for objectives 588, skills 9B8, difficulty B00, tints B18/B30;
all active direct consumers audited/replaced. Exact 1170 constructor evidence
is in native lab/LoreRimLANRest/RECOVERY-STATUS.md. Build passed. Installed
host hash now `21b025d88b08502a57b8befafe895da51a9a33e7ef59126c85b44e7d68f95e34`.
Host relaunched PID 30780 at 22:37:43, still finishing startup at last check.
UPDATE: actual main menu now verified. Automated Continue click/Return moved
the pointer but did not load; stopped repeated input. User asked to load same
save and stop BEFORE connecting for read-only field inspection. Await reply.
At startup read-only field inspection passed (empty objectives/tints, valid
skills pointer, difficulty 1). Need inspect again AFTER same-save load before
retrying connection. Script in October 23 task:
`work/check_player_fields_live.py 30780`. Crash evidence saved privately under
`work/sleep-test-v06/crash-223348`. No sleep test yet. No new saves created;
latest host pair remains Save13, 21:44:08. Terra production server untouched.

LATEST RUNTIME: user asked Codex to launch. MO2 was locked by orphan TPProcess
helpers; its Unlock button restored Run, then Codex clicked LoreRim LAN Test.
Host PID 27872 launched at 22:24:35 and reached the actual LoreRim main menu
(Continue/New/Load/Quit verified visually). It is left running there, no save
loaded. Read-only extension inspection passes: both animation strings have
allocator 0x18015D968, allocation code 0x18098D7F0, length 0/capacity 15.
Evidence: October 23 task `work/sleep-test-v06/player-extension-main-menu.json`.
This verifies initialization, not save-load acceptance. Next: same-save load
test, then magicka/exhaustion and isolated-server sleep tests if stable.

UPDATE after another crash at 22:15:47: the location candidate ran but hit
`CachedString::operator=` from `HookPerformAction` copying into player co-op
state. Dump instructions prove 1170 allocates player size 0xBE8, whereas the
client allocator only recognized 0xBF0 and missed extension construction.
Native commit `732c059` recognizes 1170's allocation and reserves the larger
existing extension layout. Build passed; installed host client SHA256 now
`38859674be80112e5add730d9cc1e256f555564ed462a2dac74ecc4c4524f518`.
The user was asked to launch to the main menu and stop there for read-only
inspection, BEFORE another save-load attempt. Run October 23 task's
`work/check_player_extension_live.py <current PID>` and preserve output.
No game process existed at the last check. Latest evidence is preserved in
`work/sleep-test-v06/crash-221547`; native recovery doc has precise addresses.
Do not mistake the superseded hash below for the installed candidate.

The authoritative native tree now has local commits `b83b5e4` (1170 VM and
sleep recovery) and `d42e1b5` (save-load Discord crash). These are experimental,
not yet synchronized into this helper overlay or pushed. See native
`lab/LoreRimLANRest/RECOVERY-STATUS.md` for binary evidence and limits.

Two 1170 launches reached the main menu after the VM fixes. The subsequent
save-load crashed in DiscordService::OnLocationChangeEvent at 0x1806C4C7A:
raw player +0xAD8 produced invalid pointer 0xC2EAC090, despite failed Discord
initialization. The follow-up skips unavailable Discord activity and reuses
Actor::GetCurrentLocation in both discovery and Discord. Build passed;
save-load retest is pending. Installed client SHA256 is
`fb05a1152fbeabbb8f8a0c7df8e2e854a64fae0d3145b9a37ae13451e9947570`.
Protocol identity is still `lorerim-rest-recovery-v0.6`.

The host currently has the v0.6 candidate and two sleep-only overwrite PEXs,
not the original rollback runtime. Exact rollback manifest and original
binary backups are under the October 23 task's private
`work/sleep-test-v06/ROLLBACK.json` and `work/startup-1170-vmfix`. Crash logs,
matching executable/PDB are preserved in `work/sleep-test-v06/crash-220655`.
No save or actor-value edits were made. Production server PID 24400/10578
was left running; isolated v0.6 test server PID 30996/10580 is also running.
No connection or sleep test has completed. Host relaunch was requested via
MO2, but no game process was present at the last check; user was asked to
load the same save and report success/crash/no-launch. Do not claim runtime
acceptance. Existing native/manager tests passed before the location fix.

The user wants the remaining LoreRim multiplayer issues fixed, with working sleep/time/needs and co-op campaign persistence. **The latest v0.5 native build failed real startup on BOTH PCs and was rolled back. It is NOT installed or ready to apply.** Do not confuse passing build/protocol tests with gameplay acceptance.

Latest immediate issue: sleeping while connected does not advance time, does not reliably restore exhaustion, and magicka does not regenerate. The user manually ran `set Survival_ExhaustionNeedValue to 0`. The subsequent healthy-looking Active Effects list is not evidence that sleeping worked.

Read-only console output on the host character **Ze'Mofed** was visually verified:
- `player.getavinfo magickarate`: current/computed base **1.05**, Temp 0, Perm 0, Damage 0.
- `player.getavinfo magicka`: current **70**, computed/reference base **100**, Temp 0, **Perm -30**, Damage 0.
- `player.getavinfo magickaratemult`: current **0**, computed base **100**, Temp 0, **Perm -100**, Damage 0.
- The zero multiplier explains blocked regeneration. The originating mod/condition is **not confirmed**; "permanent" is an actor-value modifier category, not proof of irreversible corruption.
- No forceav/modav repair has been applied. Do not blindly add 100 or reset every stat.
- Earlier alcohol hypothesis is unconfirmed for the current effects. Current DVSMP log showed Hot Beef Stew restoring thirst to zero.
- Loose-script scan examined 14,180 winning PSC/PEX files. The only `magickaratemult` match was Rite of Arcana's ROA_QuestScript; private decompilation showed READS of that AV, not evidence it applies this modifier. Do not blame Rite of Arcana from that match.
- Official Survival Mode Improved source does implement maximum-magicka penalties through permanent AV deltas with separate bookkeeping. That supports investigating the -30, but does not identify the -100 regeneration modifier.
- Do not repeat unreliable background keyboard injection. It failed to enter console queries and opened menus; the user successfully entered the three read-only commands manually. Read game captures without changing input.

## Verified current installed state

Both games were launched successfully using the restored pre-v0.5 clients. The previous matching server was restored and verified listening on UDP 10578. Games may have changed state since; recheck before stopping anything.

Host Desktop Commander device: DESKTOP-J6TETDJ (discover its current ID with list_devices).
Partner device: Terra (discover its current ID with list_devices).

Host:
- Game/MO2: `L:\LoreRim`
- Active profile: `L:\LoreRim\profiles\LoreRim LAN Test`
- Profile saves: `saves` (MO2 virtualizes `__MO_Saves`)
- Client: `L:\LoreRim\mods\LoreRim LAN - Skyrim Together 1.8.3 (1170)\SkyrimTogetherReborn`
- Server: `L:\server`
- Main source/work root: `C:\Users\brand\Documents\Codex\2026-10-20\lorerim-lan-lab-development\work`
- Full native worktree: `<work root>\lorerim-native-staging`
- This helper repo: `<work root>\lorerim-lan-lab`
- Earlier full original source: `C:\Users\brand\Documents\Codex\2026-10-20\build-a-working-two-player-lan\work\TiltedEvolution`
- L: is a SUBST to that earlier task's `work\isolated` directory; do not overwrite a real drive mapping.

Partner's ACTIVE installation is on **F:**, verified through her desktop shortcut and MO2 gamePath. An old D: copy also exists; do not update/delete the wrong copy.
- `F:\LoreRim-LAN\LoreRim`
- Profile `profiles\LoreRim LAN Test`
- Windows account `C:\Users\oldka`
- Her before-update backups: `F:\LoreRim-LAN\update-backups\v05-20261023-202241`
- Her deployment/rollback record: `F:\LoreRim-LAN\updates\v05\APPLIED.json`

Restored matching binary hashes:
- SkyrimTogether.exe: B4316ADE189C8BD988A747EAD72953232138AC34B39D20B1CBB6360F2627E49E
- EarlyLoad.dll: CB9C6118494F05F174C04EFA2FCC9B55482BA068A9F6195931157185B889DB50
- Server runner: BBBAC51C5E34BA4CF890E61BDA33C425FE4790DE75F92E4F4561AB02CF072E18
- STServer.dll: ED61BA98478C66C4CA39BA602B7B2BBE7A8EF8AF94A3A364A7AE8A8EFD1F89E5
- The server DLL has the earlier exact binary health-broadcast guard; see SERVER-HEALTH-AND-REST-STATUS.md.
- Host pre-update backup `<helper>\applied-update-backups\v05-20261023-200310` contains four binaries, original server config/modlist and all 37 profile save files. Partner backup contains 27 save files.
- Rollback restored both pre-update mod lists; the v0.5 patch mod remains on disk but is inactive. Saves were NOT restored, edited or overwritten.
- Campaign guard is disabled. Both native identities/enrollment remain pending. No managed paired campaign checkpoint with real player saves exists.

Before rollback, both profiles had 3412 enabled plugins with identical normalized order. That comparison does not certify every plugin/BSA/DLL file.

## v0.5 failure: highest-priority engineering blocker

Source build identity `lorerim-campaign-bridge-v0.5-staged`.

1. Initial native launcher mistakenly allowed only 1.7.104.0. Installed game is 1.6.1170.0 on both PCs. A source hotfix added 1170 alongside 1.7.104 and fixed BUILD_COMMIT display dropping its first character.
2. After that check was fixed, both clients crashed during Papyrus VM initialization, before loading a save.
3. Host CrashLogger:
   - `C:\Users\brand\OneDrive\Documents\My Games\Skyrim Special Edition\SKSE\crash-2026-10-23-20-31-03.log`
   - Process 644; uptime ~119 seconds.
   - EXCEPTION_ACCESS_VIOLATION at **0x180633CE1**, instruction `call [rax+0x48]`; RAX 0x141AA0E20.
   - Next stack address 0x1807512C0, then skse64_1_6_1170.dll+E4AE and Skyrim VMInitThread.
   - Offline PDB lookup resolved these addresses only to `game_seg +0x532ce1` / `game_seg +0x6502c0`; do not claim those are identified custom C++ functions.
   - Partner also produced a new crash log at 20:31:25.
4. Root cause is **unverified**. Inspect Papyrus registration, ABI/layout and compatibility with the 1170 runtime. Do not assume merely adding a version string makes a newer upstream branch safe.
5. Relevant staged code: `Code/client/Games/Misc/BSScript.cpp`, `Games/Skyrim/Misc/BSScript.{h,cpp}`, new RestExchange/NextEquipmentActor/CampaignFollower/NextCampaignFollower registrations.
6. Current experimental source is retained, with an explicit DO-NOT-INSTALL marker in the candidate folder. The matching runtime used for successful play is the old binary set above.

## Source and build locations

This branch contains:
- `native-staging/overlay/`: source-only modified/new files relative to upstream; excludes compiled files and private decompiled third-party scripts.
- `native-staging/lorerim-v05.patch`: corresponding source-only patch.
- `native-staging/README.md`: exact upstream base, full development commit and build/reconstruction instructions.
- `campaign-manager-staging/LoreRim-Campaign-Manager/campaign_manager/`: latest Python manager, protocol/storage tests and status.
- Existing helper diagnostics and exact binary-repair tools.

The full Windows worktree is more complete than an overlay and remains the authoritative place to inspect SDK dependencies/private build inputs. Native head at handoff: e1cd251 (after the startup failure status commit). Earlier commits: 4126892 (coordinated checkpoints), 3266aac (1170 version gate). Native upstream base before task changes: 5a72cdc. Do NOT push to the native worktree's origin, which is tiltedphoques/TiltedEvolution.

Private scripts NOT published: generated extended SFF DialogueFollowerScript, decompiled vanilla dependencies, StaticSkillLevelingQuestScript and rental override sources. Their staged local versions are under `<native tree>\lab\LoreRimLANRest\source` and the private compiler directories below. Review local originals and create minimal source-preserving patchers rather than publishing decompiled scripts.

Build tools:
- `<work root>\build-tools\git\cmd\git.exe`
- `<work root>\build-tools\xmake\xmake\xmake.exe` (3.x)
- VS2022 tools under `C:\CodexBuildTools`
- Python 3.12.10 on host
- Outputs: `<native tree>\build\windows\x64\releasedbg`
- Private flat SKSE SDK PluginAPI.h: `<work root>\build-tools\reference-skse`
- Papyrus compiler: `build-tools\papyrus-compiler\PapyrusCompiler.exe`
- Champollion: `build-tools\champollion\Champollion.exe`
- Dependency sources: `build-tools\private-papyrus\source`
- SFF generated source/PEX: `build-tools\campaign-followers\staged-v031`
- Parking script PEXs: `build-tools\campaign-followers\parking-v04`
- Official SMI source was cloned read-only to `build-tools\reference-survival-mode`; check its version against the installed SMI 1.5.2 before relying on implementation details.
- Private ROA diagnosis source: `build-tools\private-papyrus\rite-of-arcana-diagnosis\ROA_QuestScript.psc`

Build ONE xmake target per invocation; nonexistent target can misleadingly report success. Check actual binaries. Targets:
`SkyrimServerRunner`, `SkyrimImmersiveLauncher`, `TPTests`, `CampaignBridgeProbe`, `LoreRimCampaignCosave`, `CampaignCosaveProbe`.

Configuration regenerates BuildInfo; stamp AFTER `xmake f -m releasedbg -y`. Client, server DLL and server runner must have the same BUILD_COMMIT. Do not ship a newly linked DLL next to an older runner.

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

Menu candidate relaunch PID10760 at23:27:06; startup log confirms opcode checks
passed and deferred-save/main-thread-UI hooks installed. Main menu pending.
