"""Build the portable Windows installer ZIP without bundling game/mod assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

PYTHON_URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
PYTHON_SHA='4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
ADAPTER_SHA='2599e9475852a61a26a8e22c85a380e34c615b119d0223bc56fe574c8c4163c4'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def build(folder,adapter):
    root=Path(__file__).resolve().parents[1]
    folder=folder.resolve()
    if folder.exists(): raise ValueError('Build folder must be new')
    folder.mkdir(parents=True)
    stage=folder/'LoreRim Together Installer';stage.mkdir()
    if sha(adapter)!=ADAPTER_SHA: raise ValueError('Use the tested adapter')
    for name in ['camera_fix.py','bsa_guard_fix.py','blink_fix.py','alttab_fix.py','transport_fix.py',
                 'jcontainers_update.py','loader_fix.py','prepare_lab.py','lancheck.py','LICENSE.txt']:
        shutil.copy2(root/name,stage/name)
    shutil.copytree(root/'installer',stage/'installer',ignore=shutil.ignore_patterns('__pycache__'))
    (stage/'adapter').mkdir();shutil.copy2(adapter,stage/'adapter/BSAMemoryMap.dll')
    shutil.copy2(root/'native/MINHOOK-LICENSE.txt',stage/'adapter/MINHOOK-LICENSE.txt')
    archive=folder/'python.zip'
    urllib.request.urlretrieve(PYTHON_URL,archive)
    if sha(archive)!=PYTHON_SHA: raise ValueError('Python archive digest mismatch')
    with zipfile.ZipFile(archive) as z:z.extractall(stage/'runtime')
    csc=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(csc),'/nologo','/target:winexe','/platform:x64',
                    '/out:'+str(stage/'Install LoreRim Together.exe'),
                    '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
                    '/reference:System.Web.Extensions.dll',str(root/'installer/Installer.cs')],check=True)
    readme='''LO RERIM TOGETHER — START HERE

1. Extract this whole ZIP to a folder on your computer.
2. Double-click Install LoreRim Together.exe.
3. Choose your existing LoreRim folder and click Install.

No commands or Python installation are needed.
Use the matching LoreRim 5.0.4.8 / Skyrim 1.6.1170 installation.
Close Skyrim and Mod Organizer first. Keep the window open during setup.
Setup downloads the required Skyrim Together and JContainers releases,
checks them, applies all fixes, and creates a Play LoreRim Together shortcut.
Large game assets are reused through hard links, not copied again.
Choose a setup folder on the SAME drive as your installed LoreRim.
Programs, scripts, plugin records and settings get their own files.
Setup checks the smaller amount of free space it needs before starting.
The two setups share assets: mod updates or asset edits can affect both.

To play: open the new desktop shortcut. Load your own character, wait for mods
to initialize, then press F2. Use the host address shown by setup and password
LoreRimLab. The host must keep the server running.

If setup fails, use Open setup log and send that log back for help.
The installer can resume setup and reapply its fixes after an interruption.
An unfinished old copy on the same drive can be converted automatically.
Stop the old installer and its copy process before starting this version.
This is a portable installer: keep all extracted files together until it finishes.

Includes our MIT-licensed tooling/adapter and the official Python runtime
(license in runtime/LICENSE.txt). It does not include LoreRim or Skyrim assets.
Two-computer gameplay and quest synchronization still need testing.
'''.replace('LO RERIM','LORERIM')
    (stage/'START HERE.txt').write_text(readme,encoding='utf-8')
    manifest={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}
    (stage/'package-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    output=folder/'LoreRim-Together-Installer.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in stage.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(folder))
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None: raise ValueError('Invalid release ZIP')
    (folder/'LoreRim-Together-Installer.sha256.txt').write_text(sha(output)+'  '+output.name+'\n')
    print(json.dumps({'zip':str(output),'sha256':sha(output),'python_archive_sha256':PYTHON_SHA,'files':len(manifest)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True)
    a=p.parse_args();build(a.output,a.adapter)
