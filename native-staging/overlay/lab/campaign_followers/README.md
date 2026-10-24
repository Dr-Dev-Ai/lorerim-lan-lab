# Staged SFF campaign adapter

`patch_sff.py` instruments the winning, privately decompiled extended-alias
DialogueFollowerScript. It rejects the obsolete supplied source, already patched
input and unexpected recruitment flow. It preserves every original property and
function, adds twelve ownership checks and two alias-reporting functions. Private
Bethesda/SFF sources and generated PEX files are not included here.

The native client uses integer FormIDs and main-thread events. The server checks
that the actor is a synced visible NPC before consulting the authenticated
campaign store. Enrollment permanently reserves its campaign owner. Standard
recruit, prepare, wait, follow, dismiss and animal entry points wait for the owner
decision before actor mutations. Existing aliases report every five seconds;
observations retain recorded waiting/death states. Full slots do not reserve a
new follower. A connection dropping while a command awaits permission cancels it.

Build the generated DialogueFollowerScript, LoreRimLANRest and updated
SkyrimTogetherPlayerAliasScript together. The winning extended-alias script,
its actual dependency defaults and compiler include paths must be used.

These are source/compile checks, not gameplay acceptance. Quick Follower Commands,
custom follower frameworks, actor parking/resume and persisted identity on every
save are still missing. Do not install this as complete follower persistence.
