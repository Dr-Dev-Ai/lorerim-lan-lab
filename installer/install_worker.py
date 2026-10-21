"""Guided install worker. Uses only the packaged standard-library Python runtime."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
import traceback
import uuid
import urllib.request
import zipfile
import camera_fix, bsa_guard_fix, blink_fix, alttab_fix, transport_fix
import jcontainers_update, lancheck, prepare_lab

ROOT = Path(__file__).resolve().parents[1]
STR_URL = 'https://github.com/tiltedphoques/TiltedEvolution/releases/download/v1.8.3/SkyrimTogether-1.8.3-windows-x64-for-1.6.1170.zip'
STR_HASH = '0b2f7edcaed6152541092a1fda759de2f407985523d69a87c9cddf0ebf9b5996'
EXCLUDED = {'downloads','cache','webcache','logs','crashdumps','__temp__'}
MAX_DESTINATION_LENGTH = 60
# Only game-readable assets are shared. Programs, plugin records, scripts,
# settings, metadata and caches always get independent physical files.
SHARED_ASSETS = {'.bsa','.ba2','.dds','.nif','.hkx','.wav','.xwm','.fuz','.lip',
                 '.wem','.png','.jpg','.jpeg','.tga','.bmp','.tif','.tiff',
                 '.mp3','.ogg','.flac','.tri','.bto','.btr','.btt','.lod','.cgid'}

def event(message, progress=0):
    print(json.dumps({'message': message, 'progress': progress}), flush=True)

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(temp, path)

def clean_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('Please choose a regular folder, not a linked folder: '+str(path))
    return path.resolve()

def separate(a,b):
    if a == b or a in b.parents or b in a.parents:
        raise ValueError('Choose a separate destination outside the existing LoreRim folder.')

def version(path):
    api = ctypes.WinDLL('version', use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes=[ctypes.c_wchar_p,ctypes.c_void_p]
    size=api.GetFileVersionInfoSizeW(str(path),None)
    if not size: raise ValueError('Cannot read the Skyrim game version.')
    buf=ctypes.create_string_buffer(size)
    api.GetFileVersionInfoW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    if not api.GetFileVersionInfoW(str(path),0,size,buf): raise ctypes.WinError()
    ptr=ctypes.c_void_p();length=ctypes.c_uint()
    api.VerQueryValueW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_uint)]
    if not api.VerQueryValueW(buf,'\\',ctypes.byref(ptr),ctypes.byref(length)): raise ctypes.WinError()
    words=ctypes.cast(ptr,ctypes.POINTER(ctypes.c_uint32))
    return (words[2]>>16,words[2]&65535,words[3]>>16,words[3]&65535)

def selected_profile(source):
    text=(source/'ModOrganizer.ini').read_text(encoding='utf-8-sig')
    match=re.search(r'selected_profile=@ByteArray\((.*?)\)',text)
    if not match or not (source/'profiles'/match[1]/'modlist.txt').is_file():
        raise ValueError('Open normal LoreRim once, select its usual profile, then close it and try again.')
    if match[1] == prepare_lab.PROFILE:
        raise ValueError('Choose your normal LoreRim installation, not an existing LAN lab.')
    return match[1]

def plugin_signature(source,profile):
    names=[n.casefold() for n in lancheck.active_plugins(source,profile)
           if n.casefold() not in ('skyrimtogether.esp','skyrimtogetherquestpatches.esp')]
    return hashlib.sha256('\n'.join(names).encode()).hexdigest(),len(names)

def preflight(source,lab,check_running=True):
    source,lab=clean_path(source),clean_path(lab)
    separate(source,lab)
    separate(source,ROOT);separate(lab,ROOT)
    if len(str(lab))>MAX_DESTINATION_LENGTH: raise ValueError('Choose a shorter destination, such as D:\\LoreRim-LAN\\LoreRim.')
    if not source.is_dir(): raise ValueError('Choose the folder where LoreRim is installed.')
    for name in ['ModOrganizer.exe','ModOrganizer.ini','mods','profiles','Stock Game/SkyrimSE.exe']:
        if not (source/name).exists(): raise ValueError('This is not the LoreRim folder. Select the folder containing ModOrganizer.exe.')
    if version(source/'Stock Game/SkyrimSE.exe') != (1,6,1170,0):
        raise ValueError('This installer needs Skyrim 1.6.1170 from LoreRim 5.0.4.8. Your game version differs.')
    profile=selected_profile(source)
    baseline=json.loads((ROOT/'installer/host-baseline.json').read_text())
    signature,count=plugin_signature(source,profile)
    if signature != baseline['plugin_signature']:
        raise ValueError('This LoreRim profile does not match the host plugin list. Select the matching LoreRim 5.0.4.8 profile first.')
    expected={camera_fix.DLL:camera_fix.ORIGINAL_SHA256,
              bsa_guard_fix.FOLDER/'BSAMemoryMap.dll':bsa_guard_fix.NATIVE_HASH,
              blink_fix.DLL:blink_fix.HASH,alttab_fix.DLL:alttab_fix.HASH,
              Path('mods/JContainers SE/SKSE/Plugins/JContainers64.dll'):jcontainers_update.FILES['SKSE/Plugins/JContainers64.dll'][0]}
    for rel,sha in expected.items():
        if not (source/rel).is_file() or digest(source/rel)!=sha:
            raise ValueError('The installed '+rel.name+' differs from the tested version. Your original files have not been changed.')
    if digest(ROOT/'adapter/BSAMemoryMap.dll')!=bsa_guard_fix.ADAPTER_HASH:
        raise ValueError('The installer package is incomplete or damaged. Extract the complete ZIP again.')
    if check_running:
        processes=subprocess.check_output(['tasklist','/fo','csv','/nh'],text=True,creationflags=0x08000000).casefold()
        if '"robocopy.exe"' in processes:
            raise ValueError('A file copy is still running. Finish or stop the old installer copy before starting this version.')
        if any('"'+name+'"' in processes for name in ('skyrimse.exe','skyrimtogether.exe','modorganizer.exe')):
            raise ValueError('Close Skyrim and Mod Organizer on this computer, then click Install again.')
    statefile=lab.parent/'LoreRim-LAN-install-state.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else None
    if state:
        if state.get('source')!=str(source) or state.get('lab')!=str(lab) or state.get('format')!=1:
            raise ValueError('That destination belongs to another installation. Please choose a new destination.')
        if lab.exists():
            marker=json.loads((lab/'LORERIM_LAB.json').read_text(encoding='utf-8-sig'))
            if Path(marker['source']).resolve()!=source: raise ValueError('Destination marker does not match.')
    elif lab.exists() or (lab.parent/'server').exists():
        raise ValueError('The destination or its server folder already exists. Choose a new empty location.')
    return source,lab,statefile,state,profile,count

def source_size(source):
    total=0
    for base,dirs,files in os.walk(source,followlinks=False):
        relative=Path(base).relative_to(source)
        dirs[:]=[d for d in dirs if not (not relative.parts and d.casefold() in EXCLUDED)
                 and not (relative.parts and relative.parts[0].casefold()=='profiles' and d.casefold()=='saves')]
        for d in dirs:
            p=Path(base)/d
            if p.is_junction() or p.is_symlink(): raise ValueError('Linked content needs review before copying: '+str(p))
        for name in files:
            p=Path(base)/name
            if p.is_symlink(): raise ValueError('Linked content needs review before copying: '+str(p))
            total+=p.stat().st_size
    return total

def source_files(source):
    root=lancheck.longpath(source)
    for base,dirs,files in os.walk(root,followlinks=False):
        relative=Path(base).relative_to(root)
        dirs[:]=[d for d in dirs if not (not relative.parts and d.casefold() in EXCLUDED)
                 and not (relative.parts and relative.parts[0].casefold()=='profiles' and d.casefold()=='saves')]
        for d in dirs:
            p=Path(base)/d
            if p.is_junction() or p.is_symlink(): raise ValueError('Linked source folder needs review: '+str(p))
        for name in files:
            p=Path(base)/name
            if p.is_symlink(): raise ValueError('Linked source file needs review: '+str(p))
            yield p,p.relative_to(root)

def shared_asset(relative):
    # Mod Organizer's overwrite folder and generated/runtime folders may be
    # written even when their files happen to have an asset extension.
    parts=[p.casefold() for p in relative.parts]
    if any(p in ('overwrite','root','cache','logs','screenshots','enbcache','shadercache',
                 'nemesis_engine','calientetools','tools') for p in parts):return False
    in_assets=bool(parts and (parts[0]=='mods' or parts[:2]==['stock game','data']))
    return in_assets and relative.suffix.casefold() in SHARED_ASSETS

def same_volume(source,lab):
    parent=lab.parent
    while not parent.exists(): parent=parent.parent
    if source.stat().st_dev!=parent.stat().st_dev:
        raise ValueError('Choose a multiplayer folder on the SAME drive as your existing LoreRim. This version reuses its large game files instead of copying them.')

def private_size(source):
    # Reserve metadata space as well as bytes for the independent files.
    total=0;count=0
    for file,relative in source_files(source):
        count+=1
        if not shared_asset(relative):total+=file.stat().st_size
    return total+count*4096

def link_lab(source,lab,log):
    """Share immutable game assets; isolate every program/config/fix target.

    Replacing a lab hard-link entry never writes through to the source file.
    Partial old physical copies can be converted one file at a time atomically.
    """
    source,lab=clean_path(source),clean_path(lab)
    separate(source,lab)
    same_volume(source,lab)
    lab.mkdir(parents=True,exist_ok=True)
    write_json(lab/'LORERIM_LAB.json',{'source':str(source),
               'method':'shared asset hard links; private programs, scripts and settings',
               'shared_asset_extensions':sorted(SHARED_ASSETS)})
    linked=copied=private_bytes=shared_bytes=0;last=0;checked=set()
    root=lancheck.longpath(lab)
    for file,relative in source_files(source):
        target=root/relative
        # Check every parent before mkdir/replace; a resumed lab must never
        # redirect an operation through a junction into the source tree.
        for p in (target,*target.parents):
            if p in checked:continue
            if p.is_symlink() or p.is_junction():
                raise ValueError('Linked destination path needs review: '+str(relative))
            if p!=target:checked.add(p)
        target.parent.mkdir(parents=True,exist_ok=True)
        share=shared_asset(relative)
        if target.exists():
            if share and os.path.samefile(file,target):
                linked+=1;shared_bytes+=file.stat().st_size
                continue
            if target.stat().st_nlink!=1:
                raise ValueError('Unexpected shared destination file: '+str(relative))
        temporary=target.with_name('.'+uuid.uuid4().hex+'.install-tmp')
        try:
            if share:
                try:os.link(file,temporary)
                except OSError as e:
                    raise ValueError('Windows could not reuse game files on this destination. Choose a folder on the same local drive as LoreRim. '+str(e)) from e
                linked+=1;shared_bytes+=file.stat().st_size
            else:
                shutil.copy2(file,temporary)
                copied+=1;private_bytes+=file.stat().st_size
            try:os.replace(temporary,target)
            except PermissionError:
                # Only a private destination entry may have its attribute
                # changed. Never chmod a link to an original asset.
                if not target.exists() or target.stat().st_nlink!=1:raise
                target.chmod(target.stat().st_mode|stat.S_IWRITE)
                os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
        if time.monotonic()-last>1:
            event('Reusing game assets: '+str(linked)+' linked. Setting up '+str(copied)+' private files…',28)
            last=time.monotonic()
    result={'shared_files':linked,'private_files':copied,'shared_asset_bytes':shared_bytes,'copied_bytes':private_bytes}
    write_json(log,result)
    return result

def download(url,sha,path,label):
    if path.exists() and digest(path)==sha: return path
    event('Downloading '+label+'…',12)
    temporary=path.with_suffix(path.suffix+'.download')
    path.parent.mkdir(parents=True,exist_ok=True)
    request=urllib.request.Request(url,headers={'User-Agent':'LoreRim-LAN-Installer/1'})
    try:
        with urllib.request.urlopen(request,timeout=60) as response,temporary.open('wb') as out:
            total=int(response.headers.get('Content-Length',0));received=0;last=0
            while chunk:=response.read(1024*1024):
                out.write(chunk);received+=len(chunk)
                if time.monotonic()-last>1:
                    event('Downloading '+label+': '+str(received//1048576)+' MB'+(' of '+str(total//1048576)+' MB' if total else ''),12)
                    last=time.monotonic()
        if digest(temporary)!=sha: raise ValueError(label+' download failed its integrity check. Please retry.')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return path

def extract_zip(archive,target):
    target=target.resolve();target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            resolved=(target/item.filename).resolve()
            if resolved!=target and target not in resolved.parents:
                raise ValueError('Unsafe download archive path')
        z.extractall(target)

def copy_lab(source,lab,log):
    lab.mkdir(parents=True,exist_ok=True)
    write_json(lab/'LORERIM_LAB.json',{'source':str(source),'method':'guided installer; physical copies; no hardlinks'})
    excluded=[str(source/x) for x in EXCLUDED]
    excluded += [str(p/'saves') for p in (source/'profiles').iterdir() if p.is_dir()]
    args=['robocopy',str(source),str(lab),'/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/XJ','/MT:4','/NFL','/NDL','/NP','/XD',*excluded,'/LOG:'+str(log)]
    result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,creationflags=0x08000000)
    if result.returncode>=8: raise ValueError('The LoreRim copy could not finish. Check free space and click Install again. Details: '+str(log))

def recover_configuration(lab):
    """Retain partially prepared files for review; never recursively delete them."""
    snapshot=lab/'.installer-original-mo2.ini'
    if not snapshot.exists(): shutil.copy2(lab/'ModOrganizer.ini',snapshot)
    recovery=lab/'installer-recovery'/str(time.time_ns())
    for path in (lab/'profiles'/prepare_lab.PROFILE,lab/'mods'/prepare_lab.MOD,lab.parent/'server'):
        expected_parent=lab.parent if path.name=='server' else lab/('profiles' if path.name==prepare_lab.PROFILE else 'mods')
        if path.parent.resolve()!=expected_parent.resolve(): raise ValueError('Recovery path outside the owned installation')
        if path.exists():
            clean_path(path)
            recovery.mkdir(parents=True,exist_ok=True)
            os.replace(path,recovery/path.name)
    shutil.copy2(snapshot,lab/'ModOrganizer.ini')

def verify(lab):
    checks={}
    for rel,original_hash,patches in [(camera_fix.DLL,camera_fix.ORIGINAL_SHA256,camera_fix.PATCHES),
            (blink_fix.DLL,blink_fix.HASH,blink_fix.PATCHES),(alttab_fix.DLL,alttab_fix.HASH,alttab_fix.PATCHES),
            (transport_fix.DLL,transport_fix.HASH,transport_fix.PATCHES)]:
        folder={camera_fix.DLL:'camera',blink_fix.DLL:'blink',alttab_fix.DLL:'alttab',transport_fix.DLL:'transport'}[rel]+'-fix-backup'
        expected=camera_fix.patch_bytes((lab/folder/(rel.name+'.original')).read_bytes(),original_hash,patches)
        if (lab/rel).read_bytes()!=expected: raise ValueError('Final verification failed: '+rel.name)
        checks[rel.name]=digest(lab/rel)
    if digest(lab/bsa_guard_fix.FOLDER/'BSAMemoryMap.dll')!=bsa_guard_fix.ADAPTER_HASH: raise ValueError('Adapter verification failed')
    if digest(lab/bsa_guard_fix.FOLDER/'BSAMemoryMap.native.bin')!=bsa_guard_fix.NATIVE_HASH: raise ValueError('Native plugin verification failed')
    for rel,(_,new) in jcontainers_update.FILES.items():
        if digest(lab/'mods/JContainers SE'/rel)!=new: raise ValueError('JContainers release verification failed: '+rel)
    plugins=lancheck.active_plugins(lab,prepare_lab.PROFILE)
    baseline=json.loads((ROOT/'installer/host-baseline.json').read_text())
    if plugin_signature(lab,prepare_lab.PROFILE)[0]!=baseline['plugin_signature'] or len(plugins)!=baseline['lan_plugin_count']:
        raise ValueError('Final plugin list does not match the host.')
    write_json(lab/'guided-install-verification.json',{'fix_hashes':checks,'plugins':len(plugins),'status':'FILES VERIFIED; TWO-PLAYER GAMEPLAY NOT YET VERIFIED'})

def shortcuts(lab,host,desktop=None):
    (lab/'HOW TO JOIN.txt').write_text('PLAY TOGETHER\n\n1. Open the Play LoreRim Together desktop shortcut.\n2. Load your own lab character and wait for mods to finish starting.\n3. Press F2 and connect to '+host+':10578\n4. Password: LoreRimLab\n5. Join the host party in Player Manager.\n\nThe host computer must have the server running.\nFirst startup can take several minutes while shaders compile.\n',encoding='utf-8')
    command=[str(ROOT/'Install LoreRim Together.exe'),'--create-shortcuts',str(lab)]
    if desktop: command+=[str(desktop)]
    subprocess.run(command,check=True,creationflags=0x08000000,stdout=subprocess.DEVNULL)

def run(source,lab,host,check_only=False,desktop=None):
    if not re.fullmatch(r'[A-Za-z0-9.-]+',host) or host in ('127.0.0.1','localhost'):
        raise ValueError('Enter the host computer LAN address, for example 10.0.0.250.')
    event('Checking your LoreRim installation…',3)
    source,lab,statefile,state,profile,count=preflight(source,lab)
    if check_only:
        event('Ready: matching Skyrim version, original fix files and '+str(count)+' plugins.',100)
        return
    if state is None:
        same_volume(source,lab)
        event('Checking space for settings and compatibility files…',6)
        needed=private_size(source)+3*1024**3
        parent=lab.parent
        while not parent.exists(): parent=parent.parent
        free=shutil.disk_usage(parent).free
        if free<needed: raise ValueError('The destination needs about '+str((needed+1024**3-1)//1024**3)+" GB free. Free space on LoreRim's drive and try again.")
        state={'format':1,'source':str(source),'lab':str(lab),'copied':False,'configured':False,'storage':'shared-assets-v1'}
        write_json(statefile,state)
    cache=lab.parent/'installer-downloads'
    archive=download(STR_URL,STR_HASH,cache/'STR-1.8.3.zip','Skyrim Together')
    # Download and verify the other dependency before beginning the large copy.
    jc=download(jcontainers_update.URL,jcontainers_update.ARCHIVE_SHA256,cache/'JContainers-4.2.13.1.7z','JContainers memory update')
    if not state['copied']:
        same_volume(source,lab)
        event('Reusing existing game assets and creating private settings…',28)
        state['storage']='shared-assets-v1';write_json(statefile,state)
        link_lab(source,lab,lab.parent/'LoreRim-link-report.json')
        state['copied']=True;write_json(statefile,state)
    package=cache/'STR'
    extract_zip(archive,package)
    if not state['configured']:
        event('Setting up the multiplayer profile…',65)
        recover_configuration(lab)
        prepare_lab.configure(source,lab,package)
        state['configured']=True;write_json(statefile,state)
    event('Applying all compatibility fixes…',78)
    # Use the verified cached JContainers release rather than downloading twice.
    staged=cache/'JContainers'
    staged.mkdir(parents=True,exist_ok=True)
    subprocess.run(['tar','-xf',str(jc),'-C',str(staged)],check=True,creationflags=0x08000000,stdout=subprocess.DEVNULL)
    camera_fix.apply(lab)
    bsa_guard_fix.apply(lab,ROOT/'adapter/BSAMemoryMap.dll')
    camera_fix.apply_exact(lab,blink_fix.DLL,blink_fix.HASH,blink_fix.PATCHES,'blink-fix-backup')
    camera_fix.apply_exact(lab,alttab_fix.DLL,alttab_fix.HASH,alttab_fix.PATCHES,'alttab-fix-backup')
    camera_fix.apply_exact(lab,transport_fix.DLL,transport_fix.HASH,transport_fix.PATCHES,'transport-fix-backup')
    jcontainers_update.install(lab,staged/'Data')
    event('Verifying the finished installation…',94)
    verify(lab)
    shortcuts(lab,host,desktop)
    state['complete']=True;write_json(statefile,state)
    event('Installed! Use the Play LoreRim Together desktop shortcut. Press F2 in-game and connect to '+host+':10578. Password: LoreRimLab',100)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True);parser.add_argument('--destination',required=True)
    parser.add_argument('--host',default='10.0.0.250');parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--desktop')
    args=parser.parse_args()
    try:
        run(Path(args.source),Path(args.destination),args.host,args.check_only,args.desktop)
    except Exception as e:
        event('Could not finish: '+str(e),-1)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
