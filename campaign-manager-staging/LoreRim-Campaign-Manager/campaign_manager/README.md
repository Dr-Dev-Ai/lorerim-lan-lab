# LoreRim Campaign Manager — staged development build v0.3.0

This build provides a working file-backup manager and durable campaign database. The default manager does **not** connect to Skyrim or enforce permissions in game. A separate compiled native bridge candidate is now available in the PC staging project; see NATIVE_STAGE_STATUS.md for its implemented paths and remaining release gates. It does not merge quests, alter .ess/.skse files, issue console commands, install mods or replace the live server. The app and API always report `game_integration: false`.

## Included

- Desktop interface and CLI for existing `.ess` + `.skse` backup pairs, profile files, paired checkpoint creation and verified export to a new directory.
- Source-file stability checks, header recognition, content hashes and immutable content-addressed backup files. Missing co-saves, changed files, incompatible supplied manifests, corrupt blobs and mismatched campaign lineages stop publication.
- SQLite journal with full synchronization, stable player/character UUIDs, hashed per-player credentials and a fixed campaign leader.
- Persistent follower records and permission decisions: another player cannot manage a registered follower, dead state cannot be overwritten by stale updates, and an offline owner parks the record without transferring ownership.
- Exclusive, expiring NPC conversation grants with generation checks; ordinary service NPCs must be explicitly classified by the leader. Unknown NPCs default to leader-only interaction. Ambient observation is allowed.
- Curated artifact definitions, permanent item instance UUIDs and one logical artifact instance per campaign. Generic identical items can have different instance IDs.
- Recoverable item transfers: reserve, acknowledge source removal, acknowledge destination addition, then commit ownership once. Cancel is refused after a game-side change has been acknowledged. Pending transfers block checkpoint creation.
- Credential-scoped loopback JSON API intended for the future native server adapter. Request JSON cannot impersonate another player by supplying a different campaign/player ID.
- Compatibility fingerprint generator for actual supplied runtime files, plus order-sensitive enabled plugin/mod lists.

These are tested **database and backup behaviors**, not tested Skyrim gameplay. No follower roster or artifact catalog has been automatically imported from your saves. Metadata is stored as supplied; complete game-object reconstruction is not implemented.

## Running

Requires Python 3.11 or newer; GUI requires Tkinter. Standard library only; no package downloads or installer actions occur.

Extract the package, then double-click `Launch-Campaign-Manager.cmd` on Windows, or run from the folder containing `campaign_manager`:

```
python -m campaign_manager gui
```

Default staging data directory: `~/LoreRimCampaignStaging`. An alternate path can be supplied **before** the subcommand:

```
python -m campaign_manager --data C:\LoreRimCampaignStaging gui
```

There is deliberately no Apply/Restore-to-game button. Export creates a new directory and refuses to overwrite an existing one. Backups recognize headers but do not fully parse Skyrim/Papyrus save internals; a successful capture is not proof that two saves represent matching quest worlds.

## First campaign

1. Generate a runtime manifest from actual files. Choose the same logical names on both computers; a manifest covers only the files you supply, not every LoreRim mod. `runtime.example.json` is an illustration and is NOT a verified installation fingerprint.

```
python -m campaign_manager fingerprint --build lorerim-lan-experimental-8bd0e9a --file "SkyrimSE.exe=L:\LoreRim\Stock Game\SkyrimSE.exe" --file "SkyrimTogether.exe=C:\path\to\the\staged\SkyrimTogether.exe" --output runtime.json
```

2. In the GUI create a campaign using the MO2 profile directory and the generated runtime JSON. Add both players. The first GUI player becomes the fixed campaign leader; credentials are written into the staging data directory, not shown in the UI.
3. Select one player, then Capture save pair. Select an existing completed `.ess` file. Its matching `.skse` must be alongside it. Select that player's matching profile/runtime manifest. Repeat for the second player using a locally accessible copy of their completed files.
4. Pair checkpoint verifies that there is one current-revision capture for every player. If campaign state changes between captures, recapture both. Only file/manifest/lineage agreement is checked; the bridge must later validate game-state agreement.
5. Export copy writes both players' files, checkpoint metadata, the checkpoint's campaign-model state, and a consistent copy of the current database for audit. **The database export is current, not automatically rewound to an old checkpoint.** Use Prepare paired recovery copy for a historical database and both save pairs instead. Applying that copy to the games is still a separate, unapproved operation.

The two PCs are not automatically networked by this manager. Each player's save files must be locally accessible for capture. A remote capture/transfer agent is pending; do not share player credentials or move one player's character save over the other's.

## Paired historical recovery

Prepare paired recovery copy in the GUI creates a NEW folder with both players'
verified `.ess`/`.skse` pairs and a separate campaign database rebuilt from the
selected checkpoint's domain state. Later transfers, conversation leases and
connection sessions are omitted; followers start parked in the database. Original
files and the current campaign are unchanged. Do not run the recovered and original
branches together. Both games and the server must be closed before any later
approved installation, and both players' saves and the database must move together.
This does not certify matching quest worlds or merge solo world progress.

CLI: `python -m campaign_manager recover --credential player-one.json --checkpoint CHECKPOINT_UUID --output C:\new-recovery-copy`

## CLI

```
python -m campaign_manager --help
python -m campaign_manager init --name "Our LoreRim campaign" --profile "L:\LoreRim\profiles\LoreRim LAN Test" --runtime runtime.json
python -m campaign_manager add-player --campaign CAMPAIGN_UUID --name "Player one" --leader --credential-out player-one.json
python -m campaign_manager add-player --campaign CAMPAIGN_UUID --name "Player two" --credential-out player-two.json
python -m campaign_manager capture --credential player-one.json --save "C:\copied-saves\Save1.ess" --profile "L:\LoreRim\profiles\LoreRim LAN Test" --runtime runtime.json --operation unique-operation-001
python -m campaign_manager checkpoint --credential player-one.json --snapshot SNAPSHOT_ONE --snapshot SNAPSHOT_TWO --label "Before dungeon" --operation unique-operation-003
python -m campaign_manager export --credential player-one.json --checkpoint CHECKPOINT_UUID --output "C:\new-checkpoint-export"
```

Use persistent unique operation IDs; retry the same operation with the same payload after uncertain completion. Reusing an ID for a different action is rejected. Capture supports repeated `--extra path` arguments for known per-mod external data files. It does not automatically discover every mod's external state.

## API

```
python -m campaign_manager --data C:\LoreRimCampaignStaging serve --port 10579
```

Listens **only** on `127.0.0.1`; it is not an Internet/LAN listener. `/health` states the integration status. Other routes accept POST with `Content-Type: application/json` and `Authorization: Bearer <player credential>`. Browser-origin requests are rejected. Credentials are generated by local setup and never printed by CLI or API logs.

Routes: `/v1/me`, `/v1/session/open`, `/v1/session/heartbeat`, `/v1/session/close`, `/v1/followers/observe`, `/v1/state`, `/v1/presence`, `/v1/permission`, `/v1/followers/register`, `/v1/followers/state`, `/v1/npcs/rule`, `/v1/dialogue/acquire`, `/v1/dialogue/check`, `/v1/dialogue/renew`, `/v1/dialogue/release`, `/v1/artifacts/define`, `/v1/items/register`, `/v1/transfers/prepare`, `/v1/transfers/ack`, `/v1/transfers/abort`.

Operations that mutate campaign state require an `operation` field; follower state and transfers require expected versions. Acquire returns an opaque lease token and generation. Unknown NPCs default to the leader, not an unrestricted service NPC. Native adapters must provide trusted recruitment/actor classification and game-side mutation evidence: the API cannot prove an actor was recruited, an item removed or an item added merely because it received JSON.

## Native integration release gates

See `BRIDGE_CONTRACT.md`. Existing experimental native fixes remain separate and uninstalled. Still required:

- per-save stable character identity and a reconnect lineage barrier (initial transport/credential attachment builds and passes an isolated network test);
- remaining command/inventory/framework hooks and per-topic classification (initial activation/dialogue gates are compiled but unverified in gameplay);
- trusted follower-framework observations and adapters (SFF first; custom followers individually);
- stable mapping for generated references and complete per-instance item metadata;
- all supported inventory/storage paths and idempotent game-side receipt/recovery;
- validated capture at safe game points, remote capture agent, paired ledger/save restore and reconnect barrier;
- two-player testing, rollback/crash tests in Skyrim and per-mod compatibility verification.

Until those gates pass, running this program will NOT stop your girlfriend interacting with your follower, prevent actual game dupes or park an NPC. It records and tests the persistence/permission model for the bridge to enforce.

## Validation

Run from the parent folder:

```
python -m unittest discover -s campaign_manager/tests -v
```

Tests cover database restart/replay, racing artifact registration, transfer recovery, stale versions/leases, permission checks, corruption, unsafe paths, changing save pairs, profile/lineage mismatch, paired exports and credential-scoped HTTP behavior. Fixtures contain synthetic headers; no real save files are claimed to have been parsed. GUI source compiles; Windows window startup/layout smoke testing passed, but full desktop interaction and native gameplay tests have not run. Terra remains offline.


## Connection recovery

Native connections open a connection-scoped presence lease, renew every ten
seconds and close on disconnect. The API expires orphaned sessions after 45
seconds, including when idle; expiry parks follower records and invalidates NPC
leases. Native authority expires earlier and invalidates the client's interaction
cache. Closed session tombstones reject delayed attach jobs, and stale close calls
cannot close a new connection. Heartbeats do not advance campaign revision.
Database parking remains distinct from actual NPC parking, which is pending.

The SFF adapter now stages standard command guards and existing-alias reporting;
see `../campaign_followers/README.md`. Custom followers and hotkeys remain pending.
