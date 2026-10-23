# Native campaign candidate v0.3 — incomplete, not ready to apply

Build identity: `lorerim-campaign-bridge-v0.3-staged`.

New development completed in this revision:

- Standard SFF recruitment, preparation, wait, follow, dismiss and animal paths now stage ownership guards before actor mutation. The patcher preserves the installed extended-alias script and refuses obsolete/unexpected source. Recruitment capacity checks precede new ownership claims.
- Existing primary, extra and animal aliases report through the native transport. Initial waiting aliases remain waiting; repeated observations never revive recorded dead followers or replace another player's ownership.
- New integer Papyrus/native bridge preserves complete FormIDs and uses bounded asynchronous requests. Commands awaiting permission cancel if the connection drops. Native dialogue and follower responses have separate correlation handling.
- Connection-scoped session leases renew every ten seconds. The API sweeps idle orphaned sessions after 45 seconds, parks database follower records and expires NPC leases. Native authority expires earlier and invalidates client interaction caches. Closed-session tombstones reject delayed attach; stale close calls cannot close a replacement session. Concurrent credential use is rejected.
- Paired historical recovery now prepares both save pairs and a database rebuilt from the same checkpoint domain state. It omits later transfers, sessions and leases, verifies all copied content, preserves credential hashes and leaves originals untouched. CLI and GUI expose this separate recovery-copy operation. It does not apply to game profiles.

Validation:

- Matching Windows client launcher, server DLL/runner and standalone protocol probe build successfully.
- Native protocol suite: 204 assertions across 11 cases passed.
- Isolated real native transport -> server -> API: disabled guard rejected; valid fixed-leader credential accepted; invalid credential rejected; longer attached connection completed and a native heartbeat renewal was observed. No Skyrim process was used.
- Python manager: 43 tests passed on Linux; 42 passed on Windows with the symlink privilege test skipped. Includes historical domain rewind, paired file preservation, corruption rejection, ownership conflicts, terminal follower death, lease expiry, duplicate sessions, stale close and attach-after-close rejection.
- Generated extended SFF script, LoreRimLANRest and updated player-alias script compile with zero errors/warnings. Generated sources/PEX stay private on the PC, outside installed mods.
- The earlier host save pair remains backed up; no partner pair or two-player gameplay validation exists. Terra is offline.

Still incomplete:

- Actual game-side follower parking/resume, AI ownership reconciliation, direct hotkey paths and custom follower frameworks. Database parking is not actual NPC parking.
- Per-save character identity and a reconnect lineage barrier before world synchronization. A configured credential alone does not identify the loaded character or safe branch.
- Native item-instance identity, durable game-side transfer receipts and recovery across every inventory/storage/drop path. The database item journal is not complete in-game duplication protection.
- Per-topic authority for NPCs offering mixed quest/service dialogue. A service NPC classification can currently permit locally executed quest fragments; a server quest-update restriction cannot undo them.
- Remote save capture/transport, certified safe capture points, approved deployment and live paired save/database restoration.
- Two-player regression tests and crash/reconnect tests in Skyrim. Existing staged sawmill late-entry/prop visibility, cross-session dropped-item reconciliation and blur/magicka diagnosis are also unresolved.
- Arbitrary offline quest/world merging remains unsupported.

All engine behavior remains source-only under the existing experimental authorization; no IDA/Ghidra verification ran. Do not install this as a complete campaign-persistence fix. No installed executable, mod, save or server configuration was replaced.
