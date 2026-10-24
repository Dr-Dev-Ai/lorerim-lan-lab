"""Snapshot completed source work; explicitly NOT a deployable update."""
import hashlib
import json
import shutil
from pathlib import Path

repo = Path(__file__).resolve().parent
upstream = Path(r'C:\Users\brand\Documents\Codex\2026-10-20\build-a-working-two-player-lan\work\TiltedEvolution')
output = repo / 'pending-update-source'
output.mkdir(exist_ok=True)

files = [
    'party_rest.py', 'test_party_rest.py', 'PARTY-REST.md',
    'server_health_fix.py', 'SERVER-HEALTH-AND-REST-STATUS.md',
    'native/party_rest_clock_test.cpp',
]
native_files = [
    'Code/common/DateTime.h', 'Code/common/DateTime.cpp',
    'Code/server/Services/CalendarService.h', 'Code/server/Services/CalendarService.cpp',
    'Code/server/Services/ActorValueService.cpp', 'Code/server/Services/QuestService.cpp',
]
manifest = {
    'ready_to_apply': False,
    'deployment_authorized': False,
    'status': 'BLOCKED_NATIVE_INTEGRATION',
    'tests_already_run': {
        'party_rest_policy': '16 tests passed; no game/network adapter',
        'calendar_math': '43805 cases plus year rollover passed using actual DateTime.cpp',
    },
    'already_live_before_this_request': [
        'Multiplayer death system enabled and competing death handler stopped',
        'Item drop visibility enabled; cross-player pickup still duplicates',
        'Exact-build missing-actor health broadcast guard',
    ],
    'unfinished': [
        'Rental: selecting rent immediately exits conversation; payment and bed ownership unverified',
        'Verified leader sleep trigger and completion, including interrupted sleep',
        'Real teammate fatigue/rest effects from leader-selected duration',
        'Server clock skip plus client elapsed-day/needs bookkeeping',
        'Independent Static Skill Leveling menu for players with spendable points',
        'NPC duplicate reconciliation across entry/reconnect/leadership changes',
        'Atomic dropped-item pickup, stack/metadata preservation and replica removal',
        'Sawmill and other scripted prop state/animation synchronization',
        'Furniture seating alignment: affects both leader and member',
        'Incorrect sheathed/back equipment display; drawn-weapon behavior unverified',
        'Full native builds and two-client gameplay validation',
    ],
    'diagnosed_not_proven_current': [
        'Alcohol is a strong explanation for blurred vision and magicka suppression; active effects not verified',
        'Quest stop warning is an untracked quest-log entry, not deletion of an inventory quest item',
    ],
    'blocker': (
        'TiltedEvolution/AGENTS.md explicitly requires stopping before unknown '
        'engine hook/layout/threading implementation without IDA/Ghidra MCP, '
        'and asks for approval before a source-only attempt. No such tool is available.'
    ),
    'files': {},
}

def copy(source, relative):
    dest = output / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    manifest['files'][str(relative).replace('\\', '/')] = hashlib.sha256(dest.read_bytes()).hexdigest()

for name in files:
    copy(repo / name, Path('lab') / name)
for name in native_files:
    copy(upstream / name, Path('TiltedEvolution') / name)
copy(upstream / 'AGENTS.md', Path('TiltedEvolution/AGENTS.md'))
(output / 'STATUS.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print('Prepared source snapshot:', output)
print('READY TO APPLY: FALSE')
print('Live game/server files were not changed by this preparation.')
