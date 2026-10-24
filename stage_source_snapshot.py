import base64, io, json, zipfile
from pathlib import Path
src=Path(r'C:\Users\brand\Documents\Codex\2026-10-20\build-a-working-two-player-lan\work\TiltedEvolution')
out=Path(__file__).resolve().parent/'pending-update-source'
out.mkdir(exist_ok=True)
b=io.BytesIO()
count=0
with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
    for root in ('Code/server','Code/client','Code/encoding','Code/common','GameFiles/Skyrim/scripts/source'):
        for p in (src/root).rglob('*'):
            if p.is_file() and p.suffix.lower() in ('.h','.hpp','.cpp','.inl','.lua','.psc'):
                if p.name in ('RTTI.cpp','RTTI.h'):
                    continue
                z.write(p,str(p.relative_to(src)))
                count+=1
    for name in ('AGENTS.md','xmake.lua','LICENSE'):
        z.write(src/name,name)
    for name in ('party_rest.py','test_party_rest.py'):
        z.write(Path(__file__).resolve().parent/name,'lab/'+name)
data=base64.b64encode(b.getvalue()).decode('ascii')
path=out/'source-transfer.b64'
path.write_text('\n'.join(data[i:i+128] for i in range(0,len(data),128)),encoding='ascii')
print(json.dumps({'file':str(path),'files':count,'base64_chars':len(data),'lines':(len(data)+127)//128}))
