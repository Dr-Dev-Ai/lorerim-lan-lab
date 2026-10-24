"""Read-only override tracing of the installed rental dialogue."""
from pathlib import Path
import mmap,struct,zlib,json,re
from inspect_rest_records import fields,records,z
root=Path('L:/LoreRim')
mods=[s[1:].strip() for s in (root/'profiles/LoreRim LAN Test/modlist.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('+')]
files={}
for mod in mods:
    p=root/'mods'/mod
    if p.exists():
        for f in p.iterdir():
            if f.suffix.lower() in ('.esm','.esp','.esl'): files.setdefault(f.name.lower(),f)
for f in (root/'Stock Game/Data').iterdir():
    if f.suffix.lower() in ('.esm','.esp','.esl'): files.setdefault(f.name.lower(),f)
load=[s.strip().lower() for s in (root/'profiles/LoreRim LAN Test/loadorder.txt').read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.startswith('#')]
enabled={s[1:].strip().lower() for s in (root/'profiles/LoreRim LAN Test/plugins.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('*')}
enabled.update(['skyrim.esm','update.esm','dawnguard.esm','hearthfires.esm','dragonborn.esm'])
want=set(); chain={}
def canonical(masters,fid):
    return (masters[fid>>24],fid&0xffffff) if fid>>24<len(masters) else ('?',fid&0xffffff)
seed=files['xtended stay.esp']; masters=[]
for sig,fid,fs,allf in records(seed,{b'DIAL',b'INFO',b'QUST'}):
    if sig==b'TES4': masters=[z(b).lower() for t,b in allf if t==b'MAST']+[seed.name.lower()];continue
    want.add((sig,*canonical(masters,fid)))
    for t,b in allf:
        if t in (b'PNAM',b'RNAM') and len(b)==4: want.add((b'INFO',*canonical(masters,struct.unpack('<I',b)[0])))
for name in load:
    if name not in enabled or name not in files: continue
    p=files[name]
    with open(p,'rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        size=struct.unpack_from('<I',mm,4)[0]
        masters=[z(b).lower() for t,b in fields(mm[24:24+size]) if t==b'MAST']+[name]
        def walk(start,end):
            pos=start
            while pos+24<=end:
                sig,size=struct.unpack_from('<4sI',mm,pos)
                if sig==b'GRUP':
                    kind=struct.unpack_from('<i',mm,pos+12)[0]
                    if kind!=0 or mm[pos+8:pos+12] in (b'DIAL',b'QUST'): walk(pos+24,pos+size)
                    pos+=size;continue
                flags,fid=struct.unpack_from('<II',mm,pos+8)
                key=(sig,*canonical(masters,fid))
                if key in want:
                    data=mm[pos+24:pos+24+size]
                    if flags&0x40000:data=zlib.decompress(data[4:])
                    fs=list(fields(data)); d=dict(fs)
                    row={'plugin':name,'path':str(p),'type':sig.decode(),'owner':key[1],'id':hex(key[2]),'edid':z(d.get(b'EDID',b'')),'text':z(d.get(b'FULL',b'')),'scripts':[b.decode() for b in re.findall(rb'[A-Za-z_][A-Za-z_0-9]{5,}',d.get(b'VMAD',b''))],'fields':[(t.decode(errors='replace'),b.hex()) for t,b in fs if t in (b'DATA',b'ENAM',b'RNAM',b'PNAM',b'CTDA',b'QNAM',b'VMAD')]}
                    chain.setdefault(str(key),[]).append(row)
                pos+=24+size
        walk(0,len(mm))
out=Path(__file__).parent/'pending-update-source/rental-override-chain.json';out.write_text(json.dumps(chain,indent=2))
print('MATCHED',len(chain),'records')
for key,rows in chain.items():
    print(rows[-1]['type'],rows[-1]['owner'],rows[-1]['id'],' -> '.join(x['plugin'] for x in rows),rows[-1]['scripts'][:5])
print('REPORT',out)
