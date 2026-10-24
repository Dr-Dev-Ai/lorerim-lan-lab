"""Read-only BSA index/extraction for private build dependencies; never writes into game paths."""
from pathlib import Path
import struct,sys,zlib,json
sys.path.insert(0,str(Path(__file__).parent.parent/'build-tools/python'))

def index(path):
    with open(path,'rb') as f:
        h=f.read(36)
        if len(h)!=36: raise ValueError('Truncated BSA')
        magic,v,off,flags,nfolders,nfiles,folderlen,namelen,_=struct.unpack('<4s8I',h)
        if magic!=b'BSA\0' or v not in (103,104,105) or flags&3!=3 or flags&0x40: raise ValueError('Unsupported BSA header')
        if nfiles>1000000 or nfolders>100000: raise ValueError('Invalid BSA counts')
        reclen=24 if v==105 else 16
        f.seek(off); folders=f.read(nfolders*reclen)
        f.seek(off+nfolders*reclen+nfolders+folderlen+nfiles*16)
        names=f.read(namelen).split(b'\0')
        result={}; cursor=0
        for i in range(nfolders):
            rec=folders[i*reclen:(i+1)*reclen]
            count=struct.unpack_from('<I',rec,8)[0]
            offset=struct.unpack_from('<Q' if v==105 else '<I',rec,16 if v==105 else 12)[0]
            f.seek(offset-namelen)
            n=f.read(1)[0]; folder=f.read(n).rstrip(b'\0').decode('utf-8').lower()
            rs=f.read(count*16)
            for j in range(count):
                _,size,pos=struct.unpack_from('<QII',rs,j*16)
                name=names[cursor].decode('utf-8').lower(); cursor+=1
                result[(folder+'\\'+name).replace('/','\\')]=(v,flags,size,pos)
        if cursor!=nfiles: raise ValueError('BSA file count mismatch')
        return result

def extract(path,entry):
    v,flags,size,pos=entry
    compressed=bool(flags&4)^bool(size&0x40000000)
    with open(path,'rb') as f:
        f.seek(pos); data=f.read(size&0x3fffffff)
    if flags&0x100: data=data[1+data[0]:]
    if compressed:
        expected=struct.unpack_from('<I',data)[0]
        if v==105:
            import lz4.frame
            data=lz4.frame.decompress(data[4:])
        else: data=zlib.decompress(data[4:])
        if len(data)!=expected: raise ValueError('BSA decompressed length mismatch')
    return data

if __name__=='__main__':
    game=Path('L:/LoreRim')
    names=[s[1:].strip() for s in (game/'profiles/LoreRim LAN Test/modlist.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('+')]
    pluginlist=[s[1:].strip().lower() for s in (game/'profiles/LoreRim LAN Test/plugins.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('*')]
    stems={Path(p).stem:i for i,p in enumerate(pluginlist)}
    wanted=['rentroomscript','dialoguegenericscript','ssl_loadgamealias','staticskilllevelingquestscript','form','referencealias','alias','quest','actor','actorbase','objectreference','game','utility','math','debug','stringutil','uiextensions','ski_questbase','experience','ied','globalvariable','magiceffect','spell','perk','imagespacemodifier','message','location','cell','worldspace','faction','keyword','formlist','armor','weapon','potion','book','scroll','shout','soulgem','enchantment','ammo','race','outfit','idle','topic','topicinfo','scene','actorvalueinfo']
    wanted=set('scripts\\'+n+'.pex' for n in wanted)
    output=Path(__file__).parent.parent/'build-tools/private-papyrus'
    pex=output/'pex';pex.mkdir(parents=True,exist_ok=True)
    candidates={}
    archives=[game/'Stock Game/Data/Skyrim - Misc.bsa']
    for mod in reversed(names):
        p=game/'mods'/mod
        if p.exists():
            for bsa in p.glob('*.bsa'):
                low=bsa.stem.lower()
                rank=max((v for k,v in stems.items() if low==k or low.startswith(k+' -')),default=-1)
                if rank>=0: archives.append(bsa)
    def rank(p):
        if p.parent==game/'Stock Game/Data': return -1
        low=p.stem.lower()
        return max((v for k,v in stems.items() if low==k or low.startswith(k+' -')),default=-1)
    for bsa in sorted(archives,key=rank):
        try:
            entries=index(bsa)
            for key in wanted&entries.keys(): candidates[key]=(bsa,entries[key])
        except Exception as e: print('ARCHIVE_ERROR',str(bsa),str(e))
    provenance={}
    for key,entry in candidates.items():
        path,record=entry
        (pex/Path(key).name.replace('scripts\\','')).write_bytes(extract(path,record))
        provenance[key]=str(path)
    for mod in reversed(names):
        p=game/'mods'/mod
        for key in wanted:
            f=p/Path(key.replace('\\','/'))
            if f.exists():
                (pex/f.name).write_bytes(f.read_bytes());provenance[key]=str(f)
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2))
    print('EXTRACTED',len(provenance),'scripts to',str(pex))
    for key in sorted(provenance):
        if any(w in key for w in ('rent','dialoguegeneric','ssl_','staticskill','ski_quest','experience')): print(key,provenance[key])
