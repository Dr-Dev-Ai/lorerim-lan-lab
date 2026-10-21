# Two-client acceptance tests

**Status: pending actual two-client gameplay.** Server startup and Python tests do not pass these tests. Record one row per attempt in test-matrix.csv, with both client logs, server log, screenshots/video, exact manifests, save names, elapsed time and observed behavior. A failed attempt stays in the evidence history after fixes.

## Preparation

Startup is currently blocked by the enabled conversation camera. See
[CAMERA-DIAGNOSIS.md](CAMERA-DIAGNOSIS.md) for the reproduced failure and read-only
capture procedure. A completed probe is diagnostic evidence, not a passed launch
or acceptance test. Preserve the failed attempt before trying a native repair.

1. Use two licensed PCs on wired LAN, with independent physical lab copies and new profile-local saves. Keep normal play saves outside the lab. Both PCs must use the same runtime-specific STR 1.8.3 asset.
2. Close the game, generate full manifests on both machines, and compare. Resolve every mismatch explicitly. Root/profile location may differ; gameplay content and ordering may not. Any graphics-only mismatch still blocks strict parity until reviewed rather than silently ignored.
3. Match save-resident MCM settings: Requiem damage multipliers and timescale, Experience awards, Static Skill Leveling, Respawn loss/recovery settings, Precision, SCAR, poise, dodge cost/i-frames and MCO settings. File hashes cannot see these values inside saves.
4. Start two fresh characters with the same alternate-start choice, complete initialization separately and wait for Requiem/MCM initialization. Do not connect during the Helgen sequence. Record start location and both levels.
5. Host starts the dedicated server. Host connects to 127.0.0.1:10578; guest connects to the host's real LAN address (HOST-LAN-IP:10578). Password: LoreRimLab. Use F2/right Ctrl. Host creates one party; guest joins it. Keep that party leader for the entire test playthrough.

## Matrix procedure

| ID | Procedure | Required observation |
|---|---|---|
| CONNECT | Join both clients; form party; walk/jump/crouch around each other for 5 minutes | Both see correct models, equipment and motion; two accepted clients; no duplicates or disconnects |
| DENY | In a disposable guest manifest copy change one DLL hash, one behavior hash, one ESP hash and ordering separately; run preflight | Each fails with the exact file/order. Separately test server rejecting a deliberately absent plugin only in a disposable profile, then restore it |
| ANIM | In 1st and 3rd person perform 20 light attacks, 20 heavy attacks, combos, sprint attacks and stance transitions | Observer sees correct animation family, timing and recovery; no stuck animation/sliding; record disagreements |
| BLOCK | Block and bash the same bandit with shield, then dual-wield parry where supported | Blocked-hit damage/stamina and stagger agree; no duplicated hit reactions |
| DODGE | Dodge through 20 timed attacks, forward/back/sideways, then repeat with guest attacking | Movement and custom animation visible; i-frame and stamina outcome agrees; record misses/double damage |
| DAMAGE | Fight one identifiable bandit at Embershard together; repeat with host/guest entering first | Record target health before/after 20 individual hits and 10 simultaneous hits on both clients; no extra hits or lost damage |
| PRECISION | Sweep across two nearby enemies; test a creature and enchanted weapon trail | Same victims, single intended contact damage, consistent stagger; visual trail appearance alone is insufficient |
| MAGIC | Test projectile, concentration, AoE, healing, summon, illusion and a Magic Redone scripted spell | Same targets/results, duration, resistances and summon count; no duplicated summons or persistent effects after expiry |
| AI | Let host and guest alternately draw aggro, move behind cover, and cross cell boundary | One authoritative enemy, plausible retargeting, no permanent idle/frozen/naked NPC |
| LOOT | One player loots a corpse, then both attempt the same non-quest chest item | Shared removal with exactly one awarded item; no duplication; inventory counts survive reconnect |
| EQUIP | Swap armor/weapons, enchantments and ammo; damage/repair durability if present | Correct remote equipment and gameplay values; inventory instance identity persists |
| QUEST | Leader accepts Golden Claw, retrieves quest item, completes puzzle and turns in; guest accompanies | Matching stages/objectives, correct item ownership and rewards; no blocked scenes. Only leader advances dialogue/quest items |
| COMPANIONS | Complete Vilkas training scene with MCO/perk effects active | Trainer recognizes valid hits; quest advances once; guest state agrees |
| DUNGEON | Clear Embershard and Bleak Falls, including puzzle door and boss | Shared enemies/deaths/loot; scripts and exit remain usable |
| MODQUEST | Start a VIGILANT scene, a Wyrmstooth transition and an Undeath objective on dedicated test saves | Stage, dialogue, scripted gates and quest items agree. Passing one quest does not certify the others |
| TRANSFORM | Use the installed lich/werewolf transformation available on a disposable progressed test save | Correct remote form/animation, equipment restoration and abilities; no persistent duplicate actor |
| CELL | Enter/leave an interior 10 times leader-first; then reverse entry order as a stress test | Correct location/actors/objects/weather on each client; no duplicate spawns or invisible players |
| DEATH | Kill host, recover; then guest, recover; test simultaneous deaths and lost backpack retrieval | LoreRim's configured recovery occurs once; correct losses; no competing STR teleport or duplicated backpack |
| RECONNECT | Disconnect guest during combat, rejoin; repeat host ownership loss | Enemy ownership transfers; health/loot/quest state reconciles without resurrected loot or enemies |
| SAVE | Both save separate checkpoints, disconnect, quit both clients/server, restart, load, reconnect | Same quests, progression, inventory, durability and scripted effects; no co-save crash |
| PROGRESSION | Compare kill, discovery and quest Experience awards; level up and allocate skills | Intended per-character awards and traits, no doubled XP or unwanted vanilla skill increases |
| WORLD | Test time/weather, a persistent door, shrine, theft, dropped item and player-home chest separately | Record each feature's exact behavior; disabled upstream sync features are explicit limitations requiring a decision |
| LONG | Repeat combat/transition/loot loop for 60 minutes, including one restart | No accumulating duplicates, unrecoverable desync or crashes; retain all logs |

## Measurements and evidence

- Run `measure_lan.ps1 -Peer <other-PC-IP> -Samples 100 -Output lan-rtt.csv` in both directions. This is ICMP RTT, **not** game event latency. Report successful samples, losses and errors separately. Initial wired-LAN target: p95 RTT <= 5 ms, zero observed packet loss; revise based on real hardware/network evidence.
- Capture frame presentation times with Intel PresentMon or another frame-time collector on each PC. Select the actual game process (which can be SkyrimTogether.exe), record a 5-minute idle baseline and the same 5-minute combat route. Retain raw CSV and collector version/settings. Report p50/p95/p99 frame time and stutters, not just average FPS. Initial goal: p95 <= 33.3 ms and no sustained regression >20% from each PC's isolated single-player baseline.
- For remote animation/event delay, record both screens with a shared time reference (one camera filming both is simplest). Count frames between initiating action and observer display, subtract known capture offsets, report sample count and uncertainty. Target p95 <= 150 ms for visible remote actions; this is a test criterion, not a promise.
- In a controlled encounter, select the same logical NPC on each client and record `getav health` / relevant actor values before and after attacks, or use the STR debug actor-value view where available. Console pause can distort timing, so measure agreement after settling and use video for continuous timing. Match by base identity/location/spawn, not raw runtime FormID alone.
- Initial agreement criterion: <= 1 HP difference after a 1-second settling interval; zero duplicate loot, actors, death recoveries or quest rewards; no lost quest stage. Record the actual discrepancy even when below the criterion.
- To summarize measurements, normalize to CSV columns `timestamp,metric,unit,value,status` and run `python lancheck.py metrics measurements.csv metrics.json`. Frame time (`frame_time,ms`), event lag (`event_delay,ms`) and health error (`health_error,hp`) stay separate metrics. Preserve raw data. Unit tests use synthetic fixtures and are never performance evidence.
- Logs: each lab's MO2 logs, Stock Game/SKSE logs as configured, SkyrimTogetherReborn/logs and server/logs. Save crash reports and distinguish missing dependency, native DLL load failure, crash, protocol rejection and gameplay desync.

## On failure

Stop the affected acceptance row. Reproduce from a clean lab checkpoint and identify the smallest failing interaction. Do not disable a LoreRim mod and mark the original row passed. A temporary diagnostic A/B test must be labelled as a changed configuration; a reduced-feature final solution requires the user's explicit decision. Avoid quest-console repair commands as proof that synchronization works.

Follow upstream [party/quest guidance](https://wiki.tiltedphoques.com/tilted-online/general-information/playguide). Passing the matrix supports only the exact tested installation, scenarios, hardware and runtime.
