"""Prepare private compiler dependencies from installed scripts, without deploying anything."""
from pathlib import Path
import re,subprocess,sys,shutil
from read_bsa_scripts import index,extract
base=Path(__file__).parent.parent/'build-tools'
out=base/'private-papyrus/source';out.mkdir(parents=True,exist_ok=True)
pex=base/'private-papyrus/pex';pex.mkdir(parents=True,exist_ok=True)
exe=base/'champollion/Champollion.exe'
root=Path('L:/LoreRim')
bsa=root/'Stock Game/Data/Skyrim - Misc.bsa'
entries=index(bsa)
basekeys={Path(k).stem.lower():k for k in entries if k.startswith('scripts\\') and k.endswith('.pex')}
# Original sources supplied by UIExtensions preserve optional parameter defaults.
ui=root/'mods/UIExtensions/UIExtensions.bsa'
uiindex=index(ui)
for k in uiindex:
    if k.lower().endswith('.psc'):
        (out/Path(k).name).write_bytes(extract(ui,uiindex[k]))
# Overlay actual loose source files for the few dependencies in use.
for mod,sub in [('Skyrim Script Extender (SKSE64)','Scripts/Source'),('Xtended Stay','scripts/source'),('Survival Mode Improved - SKSE','Source/Scripts')]:
    p=root/'mods'/mod/sub
    if p.exists():
        for f in p.glob('*.psc'): shutil.copyfile(f,out/f.name)
for step in range(8):
    words=set()
    for p in out.glob('*.psc'):
        words.update(w.lower() for w in re.findall(r'\b[A-Za-z_]\w*\b',p.read_text(encoding='utf-8-sig',errors='replace')))
    present={p.stem.lower() for p in out.glob('*.psc')}
    needed=(words&basekeys.keys())-present
    if not needed: break
    for name in sorted(needed):
        target=pex/(name+'.pex');target.write_bytes(extract(bsa,entries[basekeys[name]]))
        result=subprocess.run([str(exe),str(target),'-p',str(out),'--no-debug-line'],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
    print('DEPENDENCY_PASS',step+1,'added',len(needed))
print('PRIVATE_SOURCES',len(list(out.glob('*.psc'))))
