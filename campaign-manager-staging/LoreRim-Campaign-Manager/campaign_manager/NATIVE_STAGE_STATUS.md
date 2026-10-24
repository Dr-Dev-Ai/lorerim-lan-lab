# Native campaign candidate v0.5 — startup crash; rolled back

Both installed 1.6.1170 clients failed startup during Papyrus VM initialization on October 23. The launcher initially rejected 1170; correcting that gate exposed the crash. Host CrashLogger reports an access violation at shadow-game address 0x180633CE1, with SKSE registration and VMInitThread in the stack. The root cause is not yet verified. Pre-update binaries, profile mod lists and the matching server were restored; saves were not restored or modified. The development build is retained for repair.

Build identity: `lorerim-campaign-bridge-v0.5-staged`. Development remains separate from installed game/server files.

## Implemented and built

- SKSE serialization companion owns one bounded character/campaign/epoch/checkpoint identity record. Preload invalidates native admission before world replication; record parsing rejects duplicate, malformed and foreign-epoch records. Foreign plugin records are preserved by recovery-copy rewrites.
- Admission requires the exact enrolled `.ess/.skse` pair, character, campaign epoch, lineage and compatible archived profile. Normal gameplay transport and auto-party publication wait for admission. Detected inventory, quest or progression changes after loading offline prevent admission. Unknown mod external state is not certified.
- Durable batched world-dirty markers invalidate stale reconnect saves. Presence heartbeats remain ephemeral. Campaign session state refreshes the companion's checkpoint/revision.
- Standard SFF guards and alias reporting preserve immutable recruiter ownership and terminal death. Native ownership reconciliation sends epoch/sequence checked parking, follow and wait policies to the current simulator. Papyrus applies waiting state without cloning, teleporting or resurrection. Custom followers and direct hotkeys remain unsupported.
- Coordinated checkpoint request pauses both peers, drains pending changes, checks profile hashes, freezes the server calendar and seals one revision. Both peers request fresh game saves and stream paired files through the authenticated native relay. The manager commits both verified pairs and the matching domain records atomically. Failures preserve the previous checkpoint. Shared ground drops must be picked up before capture; they have no durable cross-session reconstruction yet.
- Chunk uploads are ordered, hash-verified and retry-safe, including a crash between append/fsync and journal commit. Missing pairs and mismatched embedded identities cannot commit. Pending transfers block capture/reconnect.
- CLI `coop-save`, `coop-status`, `coop-abort`; GUI save request and window-owned loopback adapter. Generated native INI remains disabled and private. Historical recovery prepares new paired files and a new epoch in a separate folder.

## Verification

- Windows server runner/DLL and client launcher compile with matching build identity.
- Native protocol: 225 assertions in 13 cases pass.
- Companion DLL mock-SKSE lifecycle/ABI probe passes serialization, preload invalidation, epoch validation, malformed/duplicate rejection and legacy initialization checks.
- Python persistence: 63 tests pass on Linux; Windows runs 63 with one symlink privilege skip.
- Native admission probe: 10 cases pass, including absent/invalid proof, wrong character/epoch/save, pre-admission packet fence and heartbeat renewal.
- Two synthetic native peers exercise the actual server coordinator/API relay: two save snapshots/four verified files commit together and both peers receive committed resume. Synthetic fixtures are not Skyrim saves validated by the game.
- Existing SFF/parking Papyrus scripts compile with zero errors/warnings in the private build workspace.

## Still required

- In-game verification of the save request ABI, pause behavior, completed save timing and both-client reload/reconnect. Source-only engine assumptions remain unverified by IDA/Ghidra under the existing experimental authorization. Compilation and protocol probes are not gameplay validation.
- Per-topic NPC authority for mixed service/quest dialogue; custom follower/framework/hotkey coverage and missed-death reconciliation.
- Native durable per-item identities/receipts and all inventory/storage paths. The database artifact journal alone does not enforce one-of-a-kind items in Skyrim.
- Sawmill prop enable/disable and late-entry synchronization; actual blur/magicka diagnosis; two-client rental/rest/equipment/drop regression tests.
- Arbitrary offline quest/world merges remain unsupported. This candidate does not import arbitrary solo progress.

No installed executable, mod, save or server configuration was replaced. Do not present this candidate as the complete requested fix.
