"""Exercise the real native relay with two synthetic peers; never launches Skyrim."""
import argparse,base64,json,os,shutil,struct,subprocess,threading,time,uuid
from pathlib import Path
from campaign_manager.api import Server
from campaign_manager.store import Store
from campaign_manager import checkpoints,cosave,admission,coopsave

def record_bytes(record):
    data=cosave.encode_record(record)
    chunk=struct.pack('<III',cosave.RECORD_ID,1,len(data))+data
    return struct.pack('<4sIIII',b'SKSE',1,0,0,1)+struct.pack('<III',cosave.PLUGIN_ID,1,len(chunk))+chunk

def wait_until(test,seconds=20):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=test()
        if value:return value
        time.sleep(.05)
    raise RuntimeError('Timed out waiting for the native checkpoint coordinator')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();build=Path(args.build);out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    store=Store(out/'database');profile=out/'profile';profile.mkdir()
    (profile/'plugins.txt').write_text('*Skyrim.esm\n');(profile/'modlist.txt').write_text('+Fixture\n')
    runtime={'test_fixture':True};campaign=store.create_campaign('Native coordinated save',checkpoints.profile_manifest(profile,runtime));cid=campaign['id']
    players=[store.add_player(cid,'Leader',True),store.add_player(cid,'Partner')]
    epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
    revision=store.campaign(cid)['revision'];records=[];credentials=[];feeds=[]
    for i,player in enumerate(players):
        record={'version':1,'character':str(uuid.uuid4()),'campaign':cid,'epoch':epoch,'checkpoint':'','revision':revision};records.append(record)
        ess=out/f'fixture-{i}.ess';ess.write_bytes(b'TESV_SAVEGAMEfixture');ess.with_suffix('.skse').write_bytes(record_bytes(record))
        admission.capture_native(store,cid,player['player'],ess,profile,runtime,str(uuid.uuid4()),settle_seconds=.1)
        feed=out/f'outbox-{i}.json';feed.write_text('[]');feeds.append(feed)
        player['proof']=dict(record,ess_sha256=checkpoints.sha_file(ess),skse_sha256=checkpoints.sha_file(ess.with_suffix('.skse')))
        player['profile']={name:checkpoints.sha_file(profile/name) for name in ('plugins.txt','modlist.txt')};player['outbox']=str(feed)
        path=out/f'credential-{i}.json';path.write_text(json.dumps(player));credentials.append(path)
    server_dir=out/'server';(server_dir/'config').mkdir(parents=True)
    for name in ('STServer.dll','SkyrimTogetherServer.exe'):shutil.copyfile(build/name,server_dir/name)
    (server_dir/'config'/'STServer.ini').write_text('[GameServer]\nuPort=10688\nuMaxPlayerCount=4\nsServerName=Isolated Save Coordinator\nsPassword=\n[LiveServices]\nbAnnounceServer=false\n[Gameplay]\nbEnableCampaignGuard=true\nuCampaignApiPort=10589\nbAutoPartyJoin=false\nbSyncPlayerCalendar=true\n')
    api=Server(out/'database',10589);thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start()
    processes=[];logs=[];result={'gameplay_tested':False}
    try:
        log=(out/'server.log').open('w');logs.append(log)
        processes.append(subprocess.Popen([str(server_dir/'SkyrimTogetherServer.exe')],cwd=server_dir,stdout=log,stderr=subprocess.STDOUT));time.sleep(2)
        if processes[0].poll() is not None:raise RuntimeError('Isolated native server exited')
        for i,credential in enumerate(credentials):
            log=(out/f'peer-{i}.log').open('w');logs.append(log)
            processes.append(subprocess.Popen([str(build/'CampaignBridgeProbe.exe'),'127.0.0.1:10688',str(credential),'coopsave'],stdout=log,stderr=subprocess.STDOUT))
        wait_until(lambda:store.db.execute('SELECT count(*) FROM player WHERE campaign=? AND online=1',(cid,)).fetchone()[0]==2)
        requested=coopsave.request(store,cid,players[0]['player'],'Transport checkpoint',str(uuid.uuid4()));proposal=requested['id']
        sealed=wait_until(lambda: (state if (state:=coopsave.status(store,cid,players[0]['player'],proposal))['state']=='saving' else None))
        for i,record in enumerate(records):
            record=dict(record,checkpoint=proposal,revision=sealed['revision'])
            uploads={'ess':b'TESV_SAVEGAME'+os.urandom(70000),'skse':record_bytes(record)}
            messages=[];sequence=10
            import hashlib
            for kind,data in uploads.items():
                for offset in range(0,len(data),coopsave.MAX_CHUNK):
                    messages.append({'id':sequence,'body':{'action':'upload','proposal':proposal,'kind':kind,'offset':offset,'total':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data[offset:offset+coopsave.MAX_CHUNK]).decode()}});sequence+=1
            temporary=feeds[i].with_suffix('.tmp');temporary.write_text(json.dumps(messages));temporary.replace(feeds[i])
        committed=wait_until(lambda:(state if (state:=coopsave.status(store,cid,players[0]['player'],proposal))['state']=='committed' else None))
        for process in processes[1:]:
            if process.wait(timeout=10):raise RuntimeError('Synthetic native peer did not receive a committed resume')
        head=store.campaign(cid)['head'];assert head==proposal
        snapshots=json.loads(store.one('SELECT snapshots FROM checkpoint WHERE id=?',(head,))['snapshots'])
        assert len(snapshots)==2
        for sid in snapshots:checkpoints.verify_snapshot(store,store.one('SELECT * FROM snapshot WHERE id=?',(sid,)))
        result.update(result='PASS',paired_snapshots=2,verified_files=len(committed['uploads']),native_peers=2)
        print(json.dumps(result,indent=2))
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate();process.wait(timeout=5)
        for log in logs:log.close()
        api.shutdown();api.server_close();thread.join(timeout=3);store.close()
        for path in credentials:path.unlink(missing_ok=True)
        (out/'RESULTS.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
