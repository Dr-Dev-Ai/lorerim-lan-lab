"""Instrument a privately decompiled *winning* SFF script without shipping it.

Only known entry points are changed. Reject missing extended-alias APIs or already
patched input. The source/PEX must remain in isolated staging until installation.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = ('SFFExtraAliases', 'SyncSFFFollowerState', 'SFF_GetExtraAliasIndexByActor',
            'SFF_PromoteExtraToPrimaryIfNeeded', 'SFF_GetTrackedFollowerCount')

def patch_source(source):
    if 'LoreRimLANRest.' in source:
        raise ValueError('Input has already been instrumented')
    for name in REQUIRED:
        if name not in source:
            raise ValueError('Input is missing the installed extended-alias API: ' + name)
    # Insert after each actor-null check, before any framework/actor mutation.
    changes = {
        'SetAnimal': ('AnimalActor', 0),
        'PrepareFollowerActor': ('FollowerActor', 1),
        'CleanupDismissedFollowerActor': ('DismissedFollowerActor', 1),
        'FollowerWait': ('FollowerActor', 3),
        'AnimalWait': ('AnimalActor', 3),
        'FollowerFollow': ('FollowerActor', 2),
        'AnimalFollow': ('AnimalActor', 2),
        'DismissFollower': ('DismissedFollowerActor', 4),
    }
    for name, (actor, command) in changes.items():
        pattern = re.compile(r'(?im)^Function '+name+r'\([^\n]*\)[\s\S]*?^EndFunction')
        matches = list(pattern.finditer(source))
        if len(matches) != 1:
            raise ValueError('Expected exactly one function: ' + name)
        match = matches[0]; body = match.group()
        check = re.compile(r'(?im)^  If !'+actor+r'\s*\n    Return\s*\n  EndIf')
        if len(list(check.finditer(body))) != 1:
            raise ValueError('Actor validation differs in ' + name)
        guard = '\n  If !LoreRimLANRest.FollowerAllowed('+actor+', '+str(command)+')\n    Return\n  EndIf'
        if name == 'DismissFollower':
            guard = ('\n  Int campaignState = 4\n  If '+actor+'.IsDead()\n'
                     '    campaignState = 5\n  EndIf\n'
                     '  If !LoreRimLANRest.FollowerAllowed('+actor+', campaignState)\n    Return\n  EndIf')
        # Permission must precede SyncSFFFollowerState, which may clear dead aliases.
        body = body.replace('  Self.SyncSFFFollowerState()\n', '', 1) if name in ('FollowerWait','FollowerFollow','DismissFollower') else body
        body = check.sub(lambda m: m.group()+guard, body, count=1)
        source = source[:match.start()]+body+source[match.end():]
    # Claim only after SFF's capacity validation. Reserving at function entry
    # would claim ownership even when recruitment was refused because slots are full.
    anchors = (
        ('  If Self.IsManagedFollower(FollowerActor)\n', '    '),
        ('    If !Self.SFF_AddExtraFollowerAlias(FollowerActor)\n', '    '),
        ('  Self.PrepareFollowerActor(FollowerActor)\n  pFollowerAlias.ForceRefTo(FollowerActor as ObjectReference)\n', '  '),
    )
    for anchor, indent in anchors:
        if source.count(anchor) != 1:
            raise ValueError('SFF recruitment/capacity flow differs')
        guard = (indent+'If !LoreRimLANRest.FollowerAllowed(FollowerActor, 0)\n'
                 +indent+'  Return\n'+indent+'EndIf\n')
        if anchor.startswith('  If Self.IsManagedFollower'):
            source = source.replace(anchor, anchor+guard)
        else:
            source = source.replace(anchor, guard+anchor)

    # This function previously mutates the actor inside one compound If. Split
    # only its entrance so the owner decision happens before any timer/alias change.
    anchor = 'Function DismissAnimal()\n'
    if source.count(anchor) != 1:
        raise ValueError('Expected one animal dismissal entry point')
    source = source.replace(anchor, anchor+
        '  Actor campaignAnimal = pAnimalAlias.GetActorReference()\n'
        '  If !LoreRimLANRest.FollowerAllowed(campaignAnimal, 4)\n'
        '    Return\n  EndIf\n')
    source += """
; Campaign observations preserve alias ownership without re-recruiting actors.
Function LoreRimCampaignReportFollowers()
  If LoreRimLANRest.CampaignFollower(0, 6) != 1
    Return
  EndIf
  Actor campaignActor = pFollowerAlias.GetActorReference()
  LoreRimCampaignReportOne(campaignActor)
  Int campaignIndex = 0
  While campaignIndex < SFFExtraAliases.Length
    ReferenceAlias campaignAlias = SFFExtraAliases[campaignIndex]
    If campaignAlias
      LoreRimCampaignReportOne(campaignAlias.GetActorReference())
    EndIf
    campaignIndex += 1
  EndWhile
  LoreRimCampaignReportOne(pAnimalAlias.GetActorReference())
EndFunction

Function LoreRimCampaignReportOne(Actor campaignActor)
  If !campaignActor
    Return
  EndIf
  If campaignActor.IsDead()
    LoreRimLANRest.CampaignFollower(campaignActor.GetFormID(), 5)
  ElseIf campaignActor.GetAV("WaitingForPlayer") > 0.0
    LoreRimLANRest.CampaignFollower(campaignActor.GetFormID(), 8)
  Else
    LoreRimLANRest.CampaignFollower(campaignActor.GetFormID(), 7)
  EndIf
EndFunction
"""
    return source

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input');parser.add_argument('output')
    args=parser.parse_args()
    source=Path(args.input).read_text(encoding='utf-8-sig')
    result=patch_source(source)
    destination=Path(args.output)
    if destination.exists():raise ValueError('Output must be a new file')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(result,encoding='utf-8')
    record={'input_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'output_sha256':hashlib.sha256(result.encode()).hexdigest(),
            'guards':12,'deployed':False,'gameplay_tested':False}
    destination.with_suffix('.audit.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record))

if __name__=='__main__':main()
