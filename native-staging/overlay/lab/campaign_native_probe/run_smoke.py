"""Isolated native transport -> server -> loopback campaign API test. No Skyrim process."""
import argparse
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from campaign_manager.api import Server
from campaign_manager import api as api_module
from unittest.mock import patch
from campaign_manager.store import Store
from campaign_manager import checkpoints,cosave,admission
import uuid
import struct

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',required=True)
    parser.add_argument('--runner',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    build=Path(args.build);out=Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    probe=build/'CampaignBridgeProbe.exe'
    if not probe.is_file():raise RuntimeError('Native probe target did not produce an executable')
    store=Store(out/'database')
    profile=out/'profile';profile.mkdir()
    (profile/'plugins.txt').write_text('*Skyrim.esm\n');(profile/'modlist.txt').write_text('+Fixture\n')
    runtime={'test_fixture':True}
    campaign=store.create_campaign('Native transport test',checkpoints.profile_manifest(profile,runtime))
    identity=store.add_player(campaign['id'],'Probe leader',True)
    epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(campaign['id'],))['epoch']
    record={'version':1,'character':str(uuid.uuid4()),'campaign':campaign['id'],'epoch':epoch,'checkpoint':'','revision':store.campaign(campaign['id'])['revision']}
    ess=out/'fixture.ess';ess.write_bytes(b'TESV_SAVEGAMEfixture')
    data=cosave.encode_record(record)
    chunk=struct.pack('<III',cosave.RECORD_ID,1,len(data))+data
    ess.with_suffix('.skse').write_bytes(struct.pack('<4sIIII',b'SKSE',1,0,0,1)+struct.pack('<III',cosave.PLUGIN_ID,1,len(chunk))+chunk)
    snapshot=admission.capture_native(store,campaign['id'],identity['player'],ess,profile,runtime,str(uuid.uuid4()),settle_seconds=.1)
    identity['proof']=dict(record,ess_sha256=checkpoints.sha_file(ess),skse_sha256=checkpoints.sha_file(ess.with_suffix('.skse')))
    credential=out/'probe-credential.json'
    credential.write_text(json.dumps(identity))
    store.close()
    server_dir=out/'server';(server_dir/'config').mkdir(parents=True)
    shutil.copyfile(args.runner,server_dir/'SkyrimTogetherServer.exe')
    shutil.copyfile(build/'STServer.dll',server_dir/'STServer.dll')
    (server_dir/'config'/'STServer.ini').write_text('''[GameServer]
uPort=10678
uMaxPlayerCount=4
sServerName=Isolated Campaign Bridge Test
sPassword=
[LiveServices]
bAnnounceServer=false
[Gameplay]
bEnableCampaignGuard=true
uCampaignApiPort=10579
bAutoPartyJoin=false
bEnableMiscQuestSync=false
bSyncPlayerCalendar=false
''')
    heartbeat_count = []
    original_dispatch = api_module.dispatch
    def tracked_dispatch(store, actor, route, body):
        result = original_dispatch(store, actor, route, body)
        if route == '/v1/session/heartbeat' and result.get('attached'): heartbeat_count.append(1)
        return result
    tracking = patch.object(api_module, 'dispatch', tracked_dispatch)
    tracking.start()
    api=Server(out/'database',10579)
    api_thread=threading.Thread(target=api.serve_forever,daemon=True);api_thread.start()
    process=None
    results=[]
    try:
        with (out/'server-output.log').open('w') as log:
            process=subprocess.Popen([str(server_dir/'SkyrimTogetherServer.exe')],cwd=server_dir,stdout=log,stderr=subprocess.STDOUT)
            time.sleep(2)
            if process.poll() is not None:raise RuntimeError('Isolated server did not stay running (exit '+str(process.returncode)+'); inspect its test log')
            for mode in ('disabled','valid','invalid','missing_proof','invalid_json','wrong_epoch','wrong_character','wrong_save','fence','heartbeat'):
                result=subprocess.run([str(probe),'127.0.0.1:10678',str(credential),mode],capture_output=True,text=True,timeout=30)
                # The probe prints status only. Never echo credential contents.
                results.append({'case':mode,'exit_code':result.returncode,'output':result.stdout[-1200:]})
                if result.returncode:raise RuntimeError('Native handshake case failed: '+mode)
                deadline=time.monotonic()+3
                while True:
                    connection=Store(out/'database')
                    try:active=connection.db.execute("SELECT 1 FROM presence_session WHERE state='active' LIMIT 1").fetchone()
                    finally:connection.close()
                    if not active:break
                    if time.monotonic()>=deadline:raise RuntimeError('Native disconnect did not close its presence session')
                    time.sleep(.02)
            if not heartbeat_count:raise RuntimeError('Native server did not renew its presence session')
            print(json.dumps({'native_heartbeats':len(heartbeat_count),'result':'PASS','cases':results,'gameplay_tested':False},indent=2))
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        api.shutdown();api.server_close();api_thread.join(timeout=3)
        tracking.stop()
        credential.unlink(missing_ok=True)
        (out/'RESULTS.json').write_text(json.dumps({'cases':results,'native_heartbeats':len(heartbeat_count),'gameplay_tested':False},indent=2))

if __name__=='__main__':main()
