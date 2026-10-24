# Installed health guard and rest development status

## Installed health fix

Only the isolated dedicated server STServer.dll was changed.
The original is preserved in server/health-fix-backup/STServer.dll.original.
server_health_fix.py verifies the exact complete original/patched SHA256,
requires the server to be stopped, and replaces the DLL atomically.
Use --restore with the server stopped to roll back.

Original SHA256:
0e8bd7a075e925eb9f674a1c5b1bd1e6fdd1a1ca371cbf73c8bb593f01997ff8
Patched SHA256:
ed61ba98478c66c4ca39ba602b7b2bbe7a8ef8af94a3a364a7ae8a8efd1f89e5

Read-only Capstone inspection resolved the health-broadcast log string xref
to the PE unwind function RVA 0x177c20..0x177e53. The view-end comparison's
conditional jump at RVA 0x177cf1 originally went to notify construction
(0x177d7a) even when the actor was absent. It now goes to the existing epilogue
at 0x177e36, before notify construction. File offset: 0x1770f1.
Old instruction: 0f8483000000. New instruction: 0f843f010000.
No valid-actor calculation, ownership selection, client protocol or client
binary was modified. Equivalent source guard added to ActorValueService.cpp.

Startup and port 10578 verified after restart. Two-player combat/unload
regression remains necessary; do not claim all sync issues are solved.

## Quest warning diagnosis

QuestService's warning is from failing to find an already-stopped/untracked
quest in the player's quest log vector. It does NOT mean the server is
deleting a physical quest item. The source message is corrected to debug
wording while preserving the party stop notification. That logging source
change is not built into the running DLL.

## Blurred vision/magicka diagnosis

The installed DVSMP log records five Black-Briar Meads and one Reserve consumed
between 23:41:28 and 23:41:30, each restoring thirst to zero.
Installed records show:
- Requiem REQ_Alcohol_DamageRegeneration: Inebriation, reduces stamina regen
  by magnitude and magicka regen by twice magnitude.
- DVSsurvivaltweaks overrides Black-Briar Mead to magnitude 60, duration 900s.
- It overrides Black-Briar Reserve to magnitude 90, duration 1200s.
- Requiem also has REQ_ISM_Drunk and alcohol UI spells.

Alcohol is therefore a strong explanation for BOTH reported symptoms.
The current active-effect list has NOT been verified. Other effects can coexist.
No actor-value cheats, blanket dispels, disabled needs, or forced removal of
permanent character abilities were applied. Repeatedly drinking to treat
thirst can perpetuate inebriation. A normal sobriety period must elapse in
active gameplay; setting only the server hour is not proof effect timers end.

## Shared rest remains unfinished

DateTime::AdvanceRestHours and CalendarService::AdvanceRestHours are added to
the native source and correctly preserve time scale and existing calendar
rollover. The standalone native test compiles the ACTUAL DateTime.cpp and
passes 43,805 calendar/time-scale cases plus an explicit year rollover.
No complete native server/client build was produced, and these new methods
are NOT in the running DLL. There is no installed automatic sleep trigger.

Party-rest coordinator and local conditional skill-menu policy pass 16 tests,
but the network/client adapters are still missing.

The installed SurvivalModeImprovedApi.psc exposes RestoreExhaustionLevel,
RestoreHungerLevel and RestoreColdLevel. A verified client-side adapter can
use the exhaustion API rather than modifying base actor values.
Shared time skipping must account for hunger/thirst progression and send
elapsed rest/date information to both clients (current SyncPlayerCalendar
is false); broadcasting only a clock hour is insufficient for complete rest.

Tavern rental dialogue/payment/bed ownership, leader sleep trigger, teammate
rest, and conditional Static Skill Leveling menu remain to be implemented
and validated with both PCs. Do not advertise these as installed features.

## Newly reported: sawmill props visible only to leader

User reports that the non-leader sees the sawmill worker but not the log
being loaded/processed, while the leader/host sees the complete animation.

Relevant local STR source evidence:
- TESObjectREFR.cpp defines OBJECT_ANIM_SYNC as 0.
- Both HookPlayAnimation and HookPlayAnimationAndWait suppress outbound
  ScriptAnimationEvent behind this compile-time flag.
- ObjectService contains send/receive handlers for ScriptAnimationRequest/
  NotifyScriptAnimation, but they use a raw runtime FormID rather than GameId.

This is a strong lead, not a verified diagnosis of this sawmill's script path.
Do not blindly enable the global flag: raw IDs can differ across clients,
events need authority/loop guards, and late-loading clients need current prop
state instead of replaying an entire production cycle.
Trace the sawmill's linked refs, enable state and animation events on both
clients. A targeted fix must synchronize state/phase without duplicating
logs, yield, activation or quest side effects. Test leader swap and late entry.

No object-animation patch has been installed.

## Newly reported: duplicate NPCs and dropped-item pickup duplication

Screenshot image(20261023-075304).png shows two identical-looking NPCs beside
one another, with Beitild under the crosshair. This confirms the visual symptom,
not whether they have distinct references or a stale remote copy.
User also reports that a teammate picking up a dropped item does not remove
the item on the other client, allowing another pickup.

Upstream feature documentation explicitly distinguishes synchronized drops
from unsupported cross-player pickup of player-dropped items:
https://wiki.tiltedphoques.com/tilted-online/general-information/features

Drop visibility working is NOT proof of correct item transfer.
The installed health guard does not repair either duplication path.
Do not delete either NPC or disable item drops without identifying live IDs
and distinguishing the vanilla/persistent reference from a remote replica.

Required dropped-item fix: stable network instance ID, one server-accepted
pickup transaction, idempotent inventory credit/removal, preserve stack count
and enchantment/charge/temper metadata, reconcile disappearance on both clients,
reject replay and simultaneous second pickup, verify reconnect behavior.

Required NPC investigation: capture base form, reference ID, server entity,
ownership epoch and local/remote status of both visible copies on both clients.
Reconcile persistent-reference reuse, spawning and stale replica cleanup.
Test cell reentry, reconnection and leadership transfer with two clients.

Until corrected, use a non-respawning shared container for exchanges and verify
the sender lost and receiver gained the intended stack. This is a workaround,
not a duplication fix. No NPC/item duplication patch is installed yet.
