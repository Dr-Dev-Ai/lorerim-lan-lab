"""Read-only rental/level-menu record diagnosis; writes reports only in this repo."""
from pathlib import Path
import json, struct, sys
from inspect_rest_records import records, z
root=Path('L:/LoreRim')
modnames=[s[1:].strip() for s in (root/'profiles/LoreRim LAN Test/modlist.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('+')]
files={}
for name in modnames:
    p=root/'mods'/name
    if p.exists():
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in ('.esp','.esm','.esl'):
                files.setdefault(f.name.lower(),f)
for f in (root/'Stock Game/Data').glob('*'):
    if f.suffix.lower() in ('.esp','.esm','.esl'): files.setdefault(f.name.lower(),f)
selected=['skyrim.esm','realisticroomrental-basic.esp','staticskillleveling.esp']
result=[]
for name in selected:
    p=files.get(name)
    if not p:
        result.append({'missing':name}); continue
    masters=[]
    for sig,fid,fs,allfields in records(p,{b'DIAL',b'INFO',b'QUST',b'GLOB'}):
        if sig==b'TES4':
            masters=[z(b).lower() for t,b in allfields if t==b'MAST']+[name]
            continue
        edid=z(fs.get(b'EDID',b'')); title=z(fs.get(b'FULL',b''))
        if name=='skyrim.esm' and not any(w in (edid+' '+title).lower() for w in ('rent','dialoguegeneric','dialogueriverwood')): continue
        if name=='realisticroomrental-basic.esp' or any(w in (edid+' '+title).lower() for w in ('rent','dialoguegeneric','dialogueriverwood','ssl_','staticskill')):
            obj={'file':str(p),'type':z(sig),'id':hex(fid),'owner':masters[fid>>24] if fid>>24<len(masters) else '?','edid':edid,'full':title,'fields':[(z(t),b.hex()) for t,b in allfields if t in (b'VMAD',b'DATA',b'ENAM',b'TPIC',b'PNAM',b'QNAM',b'QSTI',b'CTDA',b'FLTV',b'RNAM',b'NAM1')]}
            result.append(obj)
out=Path(__file__).parent/'pending-update-source/rental-records.json'
out.write_text(json.dumps(result,indent=2),encoding='utf-8')
for x in result:
    print(json.dumps({k:v for k,v in x.items() if k!='fields'}))
print('REPORT',out,'RECORDS',len(result))
