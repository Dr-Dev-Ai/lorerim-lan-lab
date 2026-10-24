"""Apply the approved v0.5 candidate on the connected host with file rollback."""
from pathlib import Path
import configparser,datetime,hashlib,json,os,shutil,sys
base=Path(r'C:\Users\brand\Documents\Codex\2026-10-20\lorerim-lan-lab-development\work')
helper=base/'lorerim-lan-lab'
candidate=helper/'pending-update-build'/'campaign-bridge-v0.5-staged'
game=Path(r'L:\LoreRim')
profile=game/'profiles'/'LoreRim LAN Test'
server=Path(r'L:\server')
client=game/'mods'/'LoreRim LAN - Skyrim Together 1.8.3 (1170)'/'SkyrimTogetherReborn'
mod_name='[NoDelete] LoreRim LAN Campaign Update v0.5'
mod=game/'mods'/mod_name
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup=helper/'applied-update-backups'/('v05-'+stamp)
data=helper/'campaign-manager-data'/'campaign-v05'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
for item in json.loads((candidate/'FILES.json').read_text(encoding='utf-8-sig')):
 path=candidate/item['path']
 if not path.is_file() or sha(path)!=item['sha256']:raise RuntimeError('Candidate integrity mismatch: '+item['path'])
if mod.exists() or data.exists():raise RuntimeError('Update or campaign store already exists; inspect before repeating')
pairs=[(candidate/'client'/name,client/name) for name in ('SkyrimTogether.exe','EarlyLoad.dll')]
pairs += [(candidate/'server'/name,server/name) for name in ('SkyrimTogetherServer.exe','STServer.dll')]
for source,target in pairs:
 if not source.is_file() or not target.is_file():raise RuntimeError('Missing deployment file: '+str(source if not source.is_file() else target))
backup.mkdir(parents=True,exist_ok=False)
originals=[]
for index,(_,target) in enumerate(pairs):
 saved=backup/'files'/str(index)/target.name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
 originals.append((target,saved))
for target,name in ((profile/'modlist.txt','modlist.txt'),(server/'config'/'STServer.ini','STServer.ini')):
 saved=backup/name;shutil.copy2(target,saved);originals.append((target,saved))
shutil.copytree(profile/'saves',backup/'saves',copy_function=shutil.copy2)
for target,saved in originals:
 if sha(target)!=sha(saved):raise RuntimeError('Backup integrity failure')
for save in (profile/'saves').iterdir():
 if save.is_file() and sha(save)!=sha(backup/'saves'/save.name):raise RuntimeError('Save backup integrity failure')
print('Backed up and verified installed binaries, configuration, mod list and all profile saves',flush=True)
try:
 for source,target in pairs:shutil.copy2(source,target)
 (mod/'Scripts').mkdir(parents=True)
 for source in (candidate/'scripts').glob('*.pex'):shutil.copy2(source,mod/'Scripts'/source.name)
 plugins=mod/'SKSE'/'Plugins';plugins.mkdir(parents=True)
 shutil.copy2(candidate/'companion'/'SKSE'/'Plugins'/'LoreRimCampaignCosave.dll',plugins/'LoreRimCampaignCosave.dll')
 listing=profile/'modlist.txt';raw=listing.read_bytes();lines=raw.decode('utf-8-sig').splitlines()
 position=0
 while position<len(lines) and lines[position].startswith('#'):position+=1
 lines.insert(position,'+'+mod_name)
 listing.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+('\r\n'.join(lines)+'\r\n').encode('utf-8'))
 config=server/'config'/'STServer.ini'
 text=config.read_text(encoding='utf-8-sig')
 import re
 if re.search(r'^\s*bEnableCampaignGuard\s*=',text,re.M|re.I):
  text=re.sub(r'^(\s*bEnableCampaignGuard\s*=).*$',r'\g<1>false',text,flags=re.M|re.I)
 else:
  text=re.sub(r'^(\[Gameplay\]\s*)$',r'\1\nbEnableCampaignGuard=false',text,count=1,flags=re.M|re.I)
 if not re.search(r'^bEnableCampaignGuard=false\s*$',text,re.M|re.I):raise RuntimeError('Could not set enrollment mode')
 config.write_text(text,encoding='utf-8',newline='\r\n')
 sys.path.insert(0,str(candidate/'manager'))
 from campaign_manager.store import Store
 from campaign_manager.checkpoints import runtime_fingerprint,profile_manifest
 from campaign_manager.configuration import write_native_config
 store=Store(data)
 try:
  runtime_files=[f'client/{target.name}={target}' for _,target in pairs[:2]]
  runtime_files += [f'server/{target.name}={target}' for _,target in pairs[2:]]
  runtime_files += [f'patch/{p.relative_to(mod).as_posix()}={p}' for p in mod.rglob('*') if p.is_file()]
  runtime=runtime_fingerprint('lorerim-campaign-bridge-v0.5-staged',runtime_files)
  campaign=store.create_campaign('LoreRim co-op campaign v0.5',profile_manifest(profile,runtime))
  players=[store.add_player(campaign['id'],'Host',True),store.add_player(campaign['id'],'Partner')]
  credentials=data/'credentials';credentials.mkdir()
  for identity in players:
   fd=os.open(credentials/(identity['player']+'.json'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
   with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(identity,stream,indent=2)
  write_native_config(store,campaign['id'],players[0]['player'],players[0]['token'],profile/'saves',plugins/'LoreRimCampaign.ini')
  (data/'runtime.json').write_text(json.dumps(runtime,indent=2),encoding='utf-8')
  (data/'SETUP.json').write_text(json.dumps({'campaign':campaign['id'],'host':players[0]['player'],'partner':players[1]['player'],'profile':str(profile),'enrollment_pending':True,'guard_enabled':False},indent=2),encoding='utf-8')
 finally:store.close()
 for source,target in pairs:
  if sha(source)!=sha(target):raise RuntimeError('Installed binary verification failed: '+target.name)
 for source in (candidate/'scripts').glob('*.pex'):
  if sha(source)!=sha(mod/'Scripts'/source.name):raise RuntimeError('Installed script verification failed: '+source.name)
 report={'applied':True,'build':'lorerim-campaign-bridge-v0.5-staged','backup':str(backup),'patch_mod':str(mod),'campaign_data':str(data),'campaign_guard_enabled':False,'enrollment_pending':True,'partner_updated':False,'files':[{'path':str(target),'sha256':sha(target)} for _,target in pairs]}
 (backup/'APPLIED.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 (helper/'LAST_APPLIED_UPDATE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
except BaseException:
 for target,saved in originals:shutil.copy2(saved,target)
 if mod.exists():shutil.rmtree(mod)
 # Preserve a partially initialized store for inspection; it is not enabled.
 (backup/'ROLLED_BACK.txt').write_text('Installed files restored after deployment failure. Inspect any partial campaign store before retrying.')
 print('Deployment failed; original installed files restored',file=sys.stderr)
 raise
