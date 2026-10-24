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

# 1170 startup and rest recovery, October 23, 2026

Build identity: `lorerim-rest-recovery-v0.6`. Experimental; host sleep acceptance
is pending. Do not deploy this as a finished campaign update.

## Startup evidence

The failing launcher SHA256 was
`b19f3afb09c69831a2d0649ec328519ab7e21a9dc6bbdce629acbdb86d82df4a`.
Its instruction at `0x180633CCD` loads `[rax+0x210]`; the call at
`0x180633CE1` then uses virtual slot `+0x48`. Source inspection ties this
sequence to the Actor-type lookup in the initial Papyrus function registration.

Read-only process inspection of the working 1.6.1170 runtime found:

- SkyrimVM at `0x143188440`, via Address Library ID 400475.
- `+0x200`: VM implementation; vtable `0x141AA0B48`, slot 09 target `0x141444F70`.
- `+0x210`: debug interface; vtable `0x141AA0E20`, matching the crash register.
  Its slot 09 contains `0x6E696863616D6C61`, not a callable code pointer.
- VM update ID 53926 resolves to `0x1409BFB00`. Instructions at
  `0x1409BFB88` and `0x1409BFC61` respectively read the freeze byte at
  `+0x680` and increment the menu-mode timer at `+0x690`.
- The live freeze value was zero while that timer was nonzero and increasing.

The version-aware VM accessor uses `+0x200` on 1170 and retains the existing
`+0x210` on 1.7.104. All direct VM consumers now use it. The client update
hook similarly uses the 1170 freeze field rather than treating its timer as
a freeze flag. The 1.7.104 layout has not been retested.

Host startup with the pointer fix reached the main menu. A second host startup
with both fixes also reached the main menu without the original crash. This
does not establish save-load, connection, or two-player gameplay acceptance.

### Save-load crash, 22:06:55

The subsequent host save-load crashed before joining a server. Matching PDB
symbols resolve `0x1806C4C7A` to `DiscordService::OnLocationChangeEvent+0x4A`.
Disassembly loads the player field at `+0xAD8` into R14, then dereferences
`[r14]`; the crash register contains invalid pointer `0xC2EAC090`. The client
log had already reported Discord initialization failure (4). This is separate
from the Papyrus startup failure and precedes the shared-rest test.

The follow-up client skips the location handler without a Discord activity
manager, and both Discord and discovery use the existing
`Actor::GetCurrentLocation()` engine getter (Address Library ID 19812) rather
than reading the fixed player offset. No replacement struct offset is guessed.
The client rebuild passes; save-load acceptance remains pending. The protocol
identity remains v0.6, with the client revision recorded by SHA256 in the private
deployment manifest. Original crash executable/PDB and logs are retained
privately; no save restoration or actor-value edits were performed.

### Animation crash, 22:15:47

The next attempt used the location-fix client (SHA256 `fb05a115...9947570`)
and crashed at `0x18065C1DD`, `CachedString::operator=+0xBD`, called from
`HookPerformAction+0x2E3` while assigning `ActorExtension::LatestAnimation`.
The string allocator pointer held ASCII `Vampire ` rather than an allocator.
This is a distinct fault; the attempt does not prove the location fix passed
save-load acceptance.

The captured dump contains the 1170 engine instructions at `0x14064A8BE`:
`mov edx,0xBE8`, followed by a call to `0x140CC40C0` (Address Library 68115,
the allocator), then the player constructor `0x14072CB40` (ID 40411).
The player deleting destructor also passes `0xBE8` at `0x140756849`.
Our `sizeof(PlayerCharacter)` is `0xBF0`; the allocator's size switch therefore
misses 1170 players and never reserves or constructs their ActorExtension.
The animation copy consequently addresses uninitialized memory outside the
player allocation. The dump omits that heap region, so its contents are only
observed through the crash registers/stack, not a full heap reconstruction.

The follow-up recognizes the 1170 allocation size and reserves the existing
larger ExPlayerCharacter layout, retaining the extension address used by all
current casts. No whole-player layout adjustment is made. Rebuild passed;
live main-menu inspection and save-load acceptance are pending. This binary
evidence is from Capstone and the captured dump, not IDA/Ghidra MCP.

On the subsequent host launch (PID 27872), read-only inspection found the
player at `0x2AE8BA080`, extension at `+0xBF0`. Both animation strings now
contain allocator `0x18015D968`, vtable `0x180466570`, allocation method
`0x18098D7F0`, length 0 and capacity 15. This verifies initialized string state
during startup, unlike the failed animation copy; it does not establish
save-load or gameplay acceptance.

### Connection crash, 22:33:48

The allocation-fix client loaded the save and handled animation events; live
inspection read `moveStop` from its valid extension string. Wrong-version and
wrong-password attempts were rejected normally. The password was then cleared
and the isolated v0.6 server accepted the player with 3492 mods at 22:33:31.
The client crashed during initial assignment, before any rest test.

Matching symbols resolve `0x1806DF750` to
`CharacterService::RequestServerAssignment+0x4E0`. Instructions load the
objective array from player `+0x590`, then dereference entry pointer RBX=0xB.
The 1170 constructor instead initializes this array at `+0x588`
(`0x14072CF24`); its destructor uses the same offset at `0x14072DDA9`.

The remaining direct player-field consumers were audited together. The
captured 1170 constructor supplies this evidence:

| Field | 1170 offset | Existing 1.7.104 offset | Evidence instruction |
| --- | --- | --- | --- |
| Objectives | 0x588 | 0x590 | 0x14072CF24 |
| Skills wrapper | 0x9B8 | 0x9C0 | 0x14072DA17 |
| Difficulty | 0xB00 | 0xB08 | 0x14072D6A1 |
| Base tints | 0xB18 | 0xB20 | 0x14072D462 |
| Overlay tints | 0xB30 | 0xB38 | 0x14072D484 (base +0x18) |

Version-aware accessors now cover those fields; assignment, campaign progress,
damage calculation, and debug views use them. No overall player struct size or
extension address changes. Constructor bytes were read from the earlier dump
of the same 1170 engine; this is Capstone evidence, not IDA/Ghidra MCP.
The client builds and is installed as SHA256
`21b025d88b08502a57b8befafe895da51a9a33e7ef59126c85b44e7d68f95e34`.
Connection and rest acceptance remain pending.

Loaded-save inspection on PID 30780 subsequently read all 11 objectives and
their quest forms, 21 valid tint entries (capacity 32), skills XP 330 and
difficulty 1. Extension strings remained initialized with `Unequip` captured.
At 22:42:29 the test server accepted the host; the client logged player
assignment (`Request id: 14, cookie: 0`) and continued actor synchronization
without the prior crash. This is single-host initial connection evidence;
party rest, two-client synchronization and reconnect/restart remain untested.
Pre-connection read-only effects still showed Weary's regeneration penalty
-200. Variable03 read as 34 in the candidate actor-value storage inspection;
maximum-magicka modifier reconciliation still needs console corroboration.

### First real party sleep result

The user confirmed sleep worked after creating a party and failed before that.
Client/server logs agree: session 1 began for 8 hours at 22:46:41, the sleeper
finished at 22:46:42, the local SMI snapshot was acknowledged at 22:46:43,
and the server accepted canonical clock advancement before sending Complete.
The client consumed Complete. Thus the server clock skip is evidenced, not
only a map/UI observation. This was one player in a party, not a two-client test.

The post-rest effect snapshot no longer contained Weary's 0x833 effect;
Variable03 candidate fell from 34 to 3. MagickaRateMult candidate still had
a permanent -100, so full regeneration/penalty acceptance is NOT established.
Other active effects and console values need checking before any repair.

Outside a party, the current script requires RestExchange(-3) (party leader)
and the server requires party membership. No Begin was logged for the earlier
unpartied sleep. Connected clients also have their normal clock simulation
disabled, so that path supplies neither the shared time skip nor corresponding
SMI relief. This remains an explicit limitation, not a successful sleep test.

## Dropped bread cannot be picked up

The user reported a dropped bread repeatedly displaying pickup feedback without
entering inventory. The client log records an item 0x65C97 drop, count -1,
at 22:49:30. The isolated server has `bEnableItemDrops=false`.

Source inspection found a deterministic mismatch: RegisterDropped tracks the
original reference regardless of that server option, and TryPickupDropped then
suppresses the engine pickup pending a claim. The server previously created
the corresponding m_drops entry only when replication was enabled, so every
claim for such a drop was rejected. The original reference was retained and
each activation repeated the same failed cycle. The previous build did not log
claim decisions; this cause is inferred from source/configuration and the
reported behavior, not a captured per-claim diagnostic.

The candidate always records valid tracked drops. A per-drop Replicated flag
controls remote ground replicas independently from claim accounting. The
picker receives its normal claim receipt; peers that never had a replica
receive an ordinary actor inventory delta without reference/claim routing.
This also fixes their negative drop delta previously being ignored by the
missing-reference branch. Live drop/claim decision diagnostics were added.
The existing checkpoint prohibition remains conservative for all active drops.

Client/server rebuilds pass; existing protocol tests pass 225 assertions in
13 cases. Those tests do not establish drop/pickup gameplay correctness.
The compiled candidate is staged privately as client SHA256
`cf712af5a558a0839cae05b1582180dfdd6c63f67f66c8b175ade8314c6fabe0`
and STServer.dll SHA256
`55b0684d7bc1a3b6422acdaf8fbc49549461bf230d5737717bd3406d2134c97c`.
It is NOT yet installed. The host remains on `21b025d8...8f95e34`.

The user was asked to disconnect, try the original bread again (disconnect
clears local claim tracking while retaining originals), save new progress and
quit before replacement. No bread was added by console, no save restored, and
neither running server was replaced. Acceptance still needs original pickup,
fresh single-item and partial-stack drops, repeated activation, and two-client
replication/competing pickup tests. Ground claims remain session-local and
do not provide durable per-item identity across restarts.

The user then confirmed the original bread was recovered after disconnecting,
saved and closed the host. The new Save14 ESS/SKSE pair (22:55:25) was copied
and hash-verified privately before replacement. The prepared client and test
server are now installed; isolated server PID 31628 started on 10580 with
replication still disabled. Production server PID 24400 was untouched. Host
PID 29096 launched with the pickup candidate. The user was asked to load
Save14, connect, note bread count, drop one, pick it up once, and compare count.
That acceptance result is pending.

No IDA/Ghidra MCP was available. Evidence above comes from Capstone disassembly
and read-only process reads, not an IDA/Ghidra database. Under AGENTS.md's
classification these layouts remain unverified through MCP. Experimental
source work without those tools was previously authorized.

## Magicka and installed SMI

The installed SMI metadata says 1.5.2. Official upstream commit
`3de7b2d` declares version 1.5.2; its `Events.h`, `Needs/NeedBase.h`,
`Needs/NeedExhaustion.h`, and `PapyrusAPI/PapyrusAPI.h` were inspected.
The later upstream checkout is 1.6.x and must not be substituted as evidence
for installed behavior.

The host's read-only active-effect snapshot contained Survival Mode spell
`0x87B` (Weary), effect `0x833` (Survival_DamageMagickaRate), magnitude -200,
without the inactive or dispelled flags. The winning DVSsurvivaltweaks record
supplies magnitude 200 for that exhaustion stage. This identifies a current
regeneration penalty; it does not prove the earlier -100 snapshot was stale.

SMI 1.5.2's exhaustion restore API calls DecreaseNeed, which force-recalculates
stage effects and applies the tracked maximum-magicka penalty delta. A direct
need-global reset bypasses that work. No forceav/modav or save edits were made.
The earlier -30 still needs corroboration with SMI's Variable03 tracker.

## Sleep changes

- Each client snapshots its own exhaustion and configured restoration rate;
  the server receives Ready only after the local script acknowledges capture.
- After canonical time advancement, restore only the difference between the
  current need and the pre-rest target. This includes the sleeper and avoids
  repeating relief already delivered by normal SMI wake handling.
- Mirror the installed SMI wake timestamp and use its public restore API,
  including a zero restore when stage/penalty reconciliation is needed.
- SMI determines each player's own rested eligibility. Leader spouse/bed
  bonuses are no longer copied to teammates by the script.
- Retain Finish/Cancel if sleep ends before the Begin receipt arrives.
- A rejected clock advancement now produces Cancel rather than a benefits receipt.
- Clear outstanding rest state when leaving a party; retire cancelled receipt IDs.

`prepare_sleep_only.py` extracts our alias's rest code without private SFF or
IED adapters. It does not enable the broader campaign scripts or patch SSL.
The test build still contains the experimental native campaign code, with its
guard disabled; it is not an isolated rebuild of the released native client.

Both full and sleep-only Papyrus variants compile with zero errors/warnings.
Client and matching server builds pass. Existing native tests pass 225 assertions
in 13 cases. Existing manager tests pass 63 cases with one Windows symlink skip.
These are not gameplay tests. Shared hunger/thirst/cold progression, effect
timer aging, personal skill menus, cancellation, repeated sleeps, and two-client
disconnect/reconnect/restart behavior still require acceptance.

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

Menu candidate relaunch PID10760 at23:27:06; startup log confirms opcode checks
passed and deferred-save/main-thread-UI hooks installed. Main menu pending.

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
