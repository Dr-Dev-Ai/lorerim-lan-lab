# Party rest and tavern rentals: integration status

Status: transaction/menu policy implemented and unit tested.
NOT installed in Skyrim. No native client adapter, rental fix or shared sleep
feature is claimed complete. The working respawn and drop configuration is
unchanged by this work.

## Requested behavior

- The current party leader chooses the sleep duration.
- A verified completed leader sleep grants that same duration of rest to each
  member of the unchanged party, without requiring a second occupied bed.
- Each character retains their own skill points and progression.
- After rest/level-up bookkeeping completes locally, open LoreRim's existing
  Static Skill Leveling menu only if that character has spendable points.
- Wait until UI is safe; never force the menu during combat, dialogue, loading,
  another skill distribution or another blocking menu.
- Duplicate completion delivery must not grant rest or open a menu twice.
- Optional world-time advancement requires all connected players' consent,
  because the clock is shared across parties.
- Restore paid tavern bed access without changing quest-owned beds globally.

## Implemented core

party_rest.py contains PartyRest (transaction coordinator) and ClientRestEffects
(local rest receipt and conditional menu policy).
test_party_rest.py covers leader authorization, identical duration, membership
and leader changes, disconnect, interrupted rest, combat, timeout, duplicate
completion, unrelated online players, consent and independent skill menus.
Run: python -m unittest test_party_rest -v

These are pure policy tests. They do not prove the game feature works.

## Verified installed components

Host lab: L:\LoreRim (subst to the isolated lab).
Active profile: LoreRim LAN Test.
Rentals: Perseids Inns and Taverns - Realistic Room Rental Enhanced.
Leveling: Static Skill Leveling Rewritten, overridden by
Static Skill Leveling Rewritten - Enhanced Script (FIX).
Its source is source/StaticSkillLevelingQuestScript.psc in that mod.

The SSL script uses the existing "LevelUp Menu", registers its UI handlers,
and receives SSL_SkillsDistributionCompleted to store local remaining points.
UpdateSkillCaps recalculates per-level points; it must NOT be called as an
ad hoc reward for every sleep, or repeat sleeping could award points again.
SSL_PointsLeftAfterLvlUp alone is not proof that all newly available points
have been accounted for. Reuse the verified leveling entry point.

## Integration still required

1. Verify a client sleep-request/completion entry point and interruption handling.
2. Obtain authoritative connection, party revision and leader identity through
   STR. Do not trust a configured character name or a claimed client role.
3. Serialize rest requests/notifications with server-instance IDs; validate
   duration and authority on server; recheck membership and safety at commit.
4. Apply actual LoreRim rest/fatigue/leveling effects locally for the received
   hours using its own compatible sleep bookkeeping.
5. Persist per-character receipts transactionally with reward application.
6. Find the existing SSL pending-point check/menu entry point and use it only
   after normal rest bookkeeping, once per completion.
7. Trace rental dialogue payment, rental quest and local bed ownership on both
   clients. Do not force ownership of every bed or delete quest references.
8. Compile/package matching client adapters for both PCs, then verify with two
   clients. Terra is currently offline in Desktop Commander.

The upstream TiltedEvolution/AGENTS.md requires verified binary evidence before
new engine hook/offset/threading assumptions. No IDA/Ghidra connector is exposed
in this session. Do not add guessed hooks or mark this enabled in an installer.

## Two-player acceptance scenarios

- Leader sleeps eight hours: both receive eight hours of appropriate rest.
- Only one character has skill points: only that character gets the menu.
- Both have points: both get their own menu, once, independently.
- Neither has points: neither gets an empty menu.
- Member disconnects, leader changes, or sleep interrupts: no full-rest reward.
- A teammate enters combat: no forced menu or unapproved world-time skip.
- Repeat the completion packet/reload: no duplicated benefit or menu.
- Rent a room on each client: gold and appropriate bed access are correct.
- Recheck working death/respawn and ground-item exchange.
