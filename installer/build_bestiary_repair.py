"""Build the standalone, reversible Bestiary HUD workaround (no mod DLL bundled)."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile

def build(output):
    output.mkdir(parents=True,exist_ok=True)
    exe=output/'Repair-LoreRim-Bestiary.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe','/nologo',
        '/target:winexe','/platform:x64','/out:'+str(exe.resolve()),
        '/reference:System.Windows.Forms.dll','/reference:System.Web.Extensions.dll',
        str(Path(__file__).with_name('BestiaryRepair.cs').resolve())],check=True)
    readme='''BESTIARY STARTUP REPAIR

Close Skyrim and Mod Organizer. Double-click Repair-LoreRim-Bestiary.exe.
It normally finds D:\\LoreRim-LAN\\LoreRim automatically. If asked, choose the
multiplayer LoreRim folder. It must contain LORERIM_LAB.json.
Then use Play LoreRim Together and check whether the title screen loads.

This is a workaround for the DragonbornsBestiary.dll+004D717 startup crash.
It disables the optional Bestiary HUD popups, including their startup creation.
The Bestiary journal, creature tracking, scripts, ESPs and load order remain.
It does not fix the separate SkyrimSE.exe+064535E crash on the host computer.
Her in-game test is still required; this is not a multiplayer stability guarantee.

No full reinstall, downloads, Python, admin rights or ChatGPT are needed.
Only the exact supported Bestiary DLL is accepted. Other versions are refused.
The original DLL and settings are backed up in bestiary-widget-repair-backup.
To undo, extract this whole ZIP and double-click Restore Bestiary Widget.cmd.
Close Skyrim and Mod Organizer before restoring as well.

If the tool reports an error, send LoreRim-Bestiary-Repair.log from the
Windows temporary folder. Do not delete or disable the whole Bestiary mod.
'''
    (output/'READ ME.txt').write_text(readme,encoding='utf-8')
    (output/'Restore Bestiary Widget.cmd').write_text('@echo off\r\nstart "" /wait "%~dp0Repair-LoreRim-Bestiary.exe" --restore\r\n',encoding='ascii')
    archive=output/'LoreRim-Bestiary-Repair.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in [exe.name,'READ ME.txt','Restore Bestiary Widget.cmd']:
            z.write(output/name,name)
    for path in [exe,archive]:
        (output/(path.name+'.sha256.txt')).write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
    print(exe.resolve())
    print(archive.resolve())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    build(p.parse_args().output)
