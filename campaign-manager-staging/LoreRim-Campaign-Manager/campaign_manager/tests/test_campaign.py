import concurrent.futures
import hashlib
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from campaign_manager.store import Store, Conflict, Denied, form_key
from campaign_manager import checkpoints
from campaign_manager.api import Server
import urllib.request
import urllib.error

ACTOR='Skyrim.esm|000A2C94'
ARTIFACT='Skyrim.esm|0004E4EE'

class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.profile=self.root/'profile'; self.profile.mkdir()
        (self.profile/'plugins.txt').write_text('# comment\n*Skyrim.esm\n*Example.esp\n')
        (self.profile/'modlist.txt').write_text('# comment\n+Example\n')
        self.runtime={'protocol':'test-build','files':{'runtime':'unit-test-fixture'}}
        manifest=checkpoints.profile_manifest(self.profile,self.runtime)
        self.store=Store(self.root/'data')
        self.cid=self.store.create_campaign('Test campaign',manifest)['id']
        self.p1=self.store.add_player(self.cid,'Player 1',True)
        self.p2=self.store.add_player(self.cid,'Player 2')
        self.a=self.p1['player']; self.b=self.p2['player']
        self.ess=self.root/'pair.ess';self.ess.write_bytes(b'TESV_SAVEGAME'+b'fake-test-payload')
        self.ess.with_suffix('.skse').write_bytes(b'SKSE'+b'fake-test-payload')
    def tearDown(self):
        self.store.close(); self.temp.cleanup()
    def op(self): return str(uuid.uuid4())
    def present(self,pid): self.store.set_presence(self.cid,pid,True,self.op())
    def follower(self):
        self.present(self.a)
        return self.store.register_follower(self.cid,self.a,ACTOR,{'framework':'vanilla'},self.op())
    def item(self):
        self.store.define_artifact(self.cid,self.a,ARTIFACT,'Test artifact',self.op())
        return self.store.register_item(self.cid,self.a,'player:'+self.a,{'name':'Tempered artifact','charge':13.5},ARTIFACT,self.op())
    def capture(self,pid):
        return checkpoints.capture(self.store,self.cid,pid,self.ess,self.profile,self.runtime,self.op(),settle_seconds=.1)
    def pair(self):
        a=self.capture(self.a); b=self.capture(self.b)
        return checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'Before dungeon',self.op())

    def test_historical_recovery_rewinds_domain_and_keeps_pairs_together(self):
        from campaign_manager.recovery import prepare_recovery
        follower=self.follower()
        item=self.item()
        cp=self.pair()
        self.store.follower_state(self.cid,self.a,ACTOR,'waiting',{},follower['version'],self.op())
        tx=self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,item['version'],self.op())
        self.store.acknowledge_transfer(self.cid,self.a,tx['id'],'source_removed',self.op())
        self.store.acknowledge_transfer(self.cid,self.b,tx['id'],'destination_added',self.op())
        before=self.store.summary(self.cid)
        target=self.root/'recovery'
        prepare_recovery(self.store,self.cid,self.a,cp['id'],target)
        recovered=Store(target/'data')
        try:
            after=recovered.summary(self.cid)
            self.assertEqual(after['head'],cp['id'])
            self.assertEqual(after['followers'][0]['state'],'following')
            self.assertEqual(after['followers'][0]['parked'],1)
            self.assertEqual(after['items'][0]['holder'],'player:'+self.a)
            self.assertEqual(after['transfers'],[])
            self.assertFalse(any(p['online'] for p in after['players']))
            self.assertEqual(recovered.authenticate(self.p1['token'])['id'],self.a)
            for pid in (self.a,self.b):
                self.assertEqual((target/'players'/pid/'save/character.ess').read_bytes(),self.ess.read_bytes())
                self.assertEqual((target/'players'/pid/'save/character.skse').read_bytes(),self.ess.with_suffix('.skse').read_bytes())
        finally:recovered.close()
        self.assertEqual(before,self.store.summary(self.cid))
        self.assertNotIn(self.p1['token'],(target/'RECOVERY.json').read_text())

    def test_historical_recovery_rejects_membership_changes_and_overwrite(self):
        from campaign_manager.recovery import prepare_recovery
        cp=self.pair()
        target=self.root/'recovery';target.mkdir()
        with self.assertRaises(Conflict):prepare_recovery(self.store,self.cid,self.a,cp['id'],target)
        with self.assertRaises(Denied):prepare_recovery(self.store,self.cid,self.b,cp['id'],self.root/'denied')
        self.store.add_player(self.cid,'Unexpected new member')
        with self.assertRaises(Conflict):prepare_recovery(self.store,self.cid,self.a,cp['id'],self.root/'changed')
        self.assertFalse((self.root/'changed').exists())

    def test_recovery_verifies_all_content_before_publishing(self):
        from campaign_manager.recovery import prepare_recovery
        cp=self.pair()
        row=self.store.one('SELECT * FROM snapshot WHERE id=?',(cp['snapshots'][0],))
        files=json.loads(row['files'])
        checkpoints.blob_path(self.store,files['save/character.skse']['sha256']).write_bytes(b'SKSE-corrupt')
        target=self.root/'corrupt-recovery'
        with self.assertRaises(Conflict):prepare_recovery(self.store,self.cid,self.a,cp['id'],target)
        self.assertFalse(target.exists())

    def test_connection_sessions_expire_and_park_owned_followers(self):
        with patch('campaign_manager.store.time.time',return_value=100):
            self.store.session(self.cid,self.a,'connection-key-00001','open')
            self.store.observe_follower(self.cid,self.a,ACTOR,'claim',self.op())
        with patch('campaign_manager.store.time.time',return_value=146):
            self.assertEqual(self.store.expire_sessions(),1)
        self.assertFalse(self.store.member(self.cid,self.a)['online'])
        self.assertEqual(self.store.summary(self.cid)['followers'][0]['parked'],1)
        with self.assertRaises(Denied):self.store.session(self.cid,self.a,'connection-key-00001','heartbeat')

    def test_connection_heartbeat_does_not_advance_campaign_revision(self):
        with patch('campaign_manager.store.time.time',return_value=100):
            self.store.session(self.cid,self.a,'connection-key-00001','open')
        revision=self.store.campaign(self.cid)['revision']
        with patch('campaign_manager.store.time.time',return_value=130):
            self.store.session(self.cid,self.a,'connection-key-00001','heartbeat')
        with patch('campaign_manager.store.time.time',return_value=150):
            self.assertEqual(self.store.expire_sessions(),0)
        self.assertEqual(self.store.campaign(self.cid)['revision'],revision)

    def test_connection_close_tombstone_and_stale_close(self):
        self.store.session(self.cid,self.a,'connection-key-00001','close')
        with self.assertRaises(Denied):self.store.session(self.cid,self.a,'connection-key-00001','open')
        self.store.session(self.cid,self.a,'connection-key-00002','open')
        self.store.session(self.cid,self.a,'connection-key-00001','close')
        self.assertTrue(self.store.member(self.cid,self.a)['online'])
        with self.assertRaises(Conflict):self.store.session(self.cid,self.a,'connection-key-00003','open')
        with self.assertRaises(Denied):self.store.session(self.cid,self.b,'connection-key-00002','close')
        self.store.session(self.cid,self.a,'connection-key-00002','close')
        self.assertFalse(self.store.member(self.cid,self.a)['online'])

    def test_native_existing_alias_observation_preserves_wait_and_death(self):
        self.present(self.b)
        row=self.store.observe_follower(self.cid,self.b,ACTOR,'seen_waiting',self.op())
        self.assertEqual(row['state'],'waiting')
        for state in ('waiting','dead'):
            self.store.observe_follower(self.cid,self.b,ACTOR,state,self.op())
            revision=self.store.campaign(self.cid)['revision']
            observed=self.store.observe_follower(self.cid,self.b,ACTOR,'seen',self.op())
            self.assertEqual(observed['state'],state)
            self.assertEqual(revision,self.store.campaign(self.cid)['revision'])
        self.present(self.a)
        with self.assertRaises(Denied):self.store.observe_follower(self.cid,self.a,ACTOR,'seen',self.op())

    def test_native_follower_claim_and_owner_transitions(self):
        self.present(self.b)
        first = self.store.observe_follower(self.cid,self.b,ACTOR,'claim',self.op())
        self.assertEqual(first['owner'],self.b)
        self.assertEqual(first['state'],'following')
        for state in ('waiting','following','dismissed','claim'):
            row = self.store.observe_follower(self.cid,self.b,ACTOR,state,self.op())
            self.assertEqual(row['state'],'following' if state=='claim' else state)
        self.present(self.a)
        with self.assertRaises(Denied):
            self.store.observe_follower(self.cid,self.a,ACTOR,'claim',self.op())
        with self.assertRaises(Denied):
            self.store.permission(self.cid,self.a,ACTOR,'command')

    def test_native_follower_claim_requires_presence_and_explicit_enrollment(self):
        with self.assertRaises(Denied):
            self.store.observe_follower(self.cid,self.b,ACTOR,'claim',self.op())
        self.present(self.b)
        with self.assertRaises(Denied):
            self.store.observe_follower(self.cid,self.b,ACTOR,'waiting',self.op())

    def test_native_follower_repeated_observations_are_idempotent(self):
        self.present(self.b)
        operation = self.op()
        first=self.store.observe_follower(self.cid,self.b,ACTOR,'claim',operation)
        revision=self.store.campaign(self.cid)['revision']
        self.assertEqual(first,self.store.observe_follower(self.cid,self.b,ACTOR,'claim',operation))
        self.assertEqual(first,self.store.observe_follower(self.cid,self.b,ACTOR,'following',self.op()))
        self.assertEqual(revision,self.store.campaign(self.cid)['revision'])
        with self.assertRaises(Conflict):
            self.store.observe_follower(self.cid,self.b,ACTOR,'waiting',operation)

    def test_native_follower_death_is_terminal_across_restarts(self):
        self.present(self.b)
        self.store.observe_follower(self.cid,self.b,ACTOR,'claim',self.op())
        dead=self.store.observe_follower(self.cid,self.b,ACTOR,'dead',self.op())
        self.store.close();self.store=Store(self.root/'data')
        self.assertEqual(dead,self.store.observe_follower(self.cid,self.b,ACTOR,'dead',self.op()))
        for state in ('claim','following','waiting','dismissed'):
            with self.assertRaises(Conflict):
                self.store.observe_follower(self.cid,self.b,ACTOR,state,self.op())

    def test_form_reference_normalization_and_rejection(self):
        self.assertEqual(form_key('Skyrim.ESM|a2c94'),'skyrim.esm|0a2c94')
        for value in ('FF123456','../bad.esp|123','X.esp|1234567','X|1','X.esp|xyz'):
            with self.assertRaises(ValueError): form_key(value)
    def test_credentials_survive_restart_and_are_hashed(self):
        self.assertEqual(self.store.authenticate(self.p1['token'])['id'],self.a)
        self.assertNotIn(self.p1['token'],str([tuple(r) for r in self.store.db.execute('SELECT * FROM player')]))
        self.store.close();self.store=Store(self.root/'data')
        self.assertEqual(self.store.authenticate(self.p1['token'])['id'],self.a)
        with self.assertRaises(Denied): self.store.authenticate('wrong')
    def test_fixed_leader_is_not_reassigned(self):
        self.store.set_presence(self.cid,self.a,False,self.op())
        self.assertEqual(self.store.campaign(self.cid)['leader'],self.a)
        with self.assertRaises(Denied): self.store.leader(self.cid,self.b)
    def test_operation_replay_changes_state_once(self):
        op=self.op(); a=self.store.set_presence(self.cid,self.a,True,op)
        b=self.store.set_presence(self.cid,self.a,True,op)
        self.assertEqual(a,b)
        self.assertEqual(a['revision'],self.store.campaign(self.cid)['revision'])
        with self.assertRaises(Conflict): self.store.set_presence(self.cid,self.a,False,op)
    def test_follower_owner_is_permanent_and_nonowner_actions_denied(self):
        self.follower()
        for action in ('talk','trade','pickpocket','command','dismiss','recruit'):
            with self.assertRaises(Denied): self.store.permission(self.cid,self.b,ACTOR,action)
        self.assertTrue(self.store.permission(self.cid,self.b,ACTOR,'observe'))
        with self.assertRaises(Conflict): self.store.register_follower(self.cid,self.b,ACTOR,{},self.op())
    def test_follower_parks_and_returns_without_owner_change(self):
        self.follower(); self.store.set_presence(self.cid,self.a,False,self.op())
        row=self.store.summary(self.cid)['followers'][0]
        self.assertEqual((row['owner'],row['parked']),(self.a,1))
        with self.assertRaises(Denied): self.store.permission(self.cid,self.a,ACTOR,'talk')
        self.present(self.a)
        self.assertTrue(self.store.permission(self.cid,self.a,ACTOR,'talk'))
    def test_dead_follower_cannot_be_restored_by_stale_state(self):
        f=self.follower()
        self.store.follower_state(self.cid,self.a,ACTOR,'dead',{},f['version'],self.op())
        with self.assertRaises(Conflict): self.store.follower_state(self.cid,self.a,ACTOR,'following',{},2,self.op())
        with self.assertRaises(Conflict): self.store.register_follower(self.cid,self.a,ACTOR,{},self.op())
    def test_quest_dialogue_requires_leader(self):
        with self.assertRaises(Denied): self.store.acquire_dialogue(self.cid,self.b,ACTOR)
        with self.assertRaises(Denied): self.store.set_npc_rule(self.cid,self.b,ACTOR,'service',self.op())
        grant=self.store.acquire_dialogue(self.cid,self.a,ACTOR)
        self.store.check_dialogue(self.cid,self.a,ACTOR,grant['token'],grant['generation'],'quest')
    def test_service_dialogue_is_exclusive_and_stale_grant_fails(self):
        self.store.set_npc_rule(self.cid,self.a,ACTOR,'service',self.op())
        first=self.store.acquire_dialogue(self.cid,self.a,ACTOR)
        with self.assertRaises(Conflict): self.store.acquire_dialogue(self.cid,self.b,ACTOR)
        self.store.release_dialogue(self.cid,self.a,ACTOR,first['token'],first['generation'])
        second=self.store.acquire_dialogue(self.cid,self.b,ACTOR)
        self.assertGreater(second['generation'],first['generation'])
        with self.assertRaises(Denied): self.store.check_dialogue(self.cid,self.a,ACTOR,first['token'],first['generation'])
        self.store.renew_dialogue(self.cid,self.b,ACTOR,second['token'],second['generation'])
    def test_expired_and_disconnected_dialogue_grants_fail(self):
        grant=self.store.acquire_dialogue(self.cid,self.a,ACTOR)
        self.store.set_presence(self.cid,self.a,False,self.op())
        with self.assertRaises(Denied): self.store.check_dialogue(self.cid,self.a,ACTOR,grant['token'],grant['generation'])
        with self.assertRaises(Denied): self.store.acquire_dialogue(self.cid,self.b,ACTOR,action='observe')
    def test_artifact_cannot_be_registered_twice_even_after_restart(self):
        self.item(); self.store.close(); self.store=Store(self.root/'data')
        with self.assertRaises(Conflict): self.store.register_item(self.cid,self.a,'player:'+self.b,{},ARTIFACT,self.op())
        self.assertEqual(len(self.store.summary(self.cid)['items']),1)
    def test_generic_identical_items_can_have_separate_identities(self):
        a=self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,self.op())
        b=self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,self.op())
        self.assertNotEqual(a['id'],b['id'])
    def test_transfer_survives_crash_and_commits_once(self):
        item=self.item()
        transfer=self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,self.op())
        with self.assertRaises(Conflict): self.store.acknowledge_transfer(self.cid,self.b,transfer['id'],'destination_added',self.op())
        self.store.acknowledge_transfer(self.cid,self.a,transfer['id'],'source_removed',self.op())
        self.store.close();self.store=Store(self.root/'data')
        with self.assertRaises(Conflict): self.store.abort_transfer(self.cid,self.a,transfer['id'],self.op())
        op=self.op()
        first=self.store.acknowledge_transfer(self.cid,self.b,transfer['id'],'destination_added',op)
        self.assertEqual(first,self.store.acknowledge_transfer(self.cid,self.b,transfer['id'],'destination_added',op))
        row=self.store.summary(self.cid)['items'][0]
        self.assertEqual((row['holder'],row['version']),('player:'+self.b,2))
        self.assertEqual(json.loads(row['metadata'])['name'],'Tempered artifact')
    def test_wrong_transfer_participant_and_concurrent_transfer_are_denied(self):
        item=self.item()
        with self.assertRaises(Denied): self.store.prepare_transfer(self.cid,self.b,item['id'],'player:'+self.a,1,self.op())
        transfer=self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,self.op())
        with self.assertRaises(Denied): self.store.acknowledge_transfer(self.cid,self.b,transfer['id'],'source_removed',self.op())
        with self.assertRaises(Conflict): self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,self.op())
        self.store.abort_transfer(self.cid,self.a,transfer['id'],self.op())
        self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,self.op())
    def test_racing_artifact_registration_has_one_winner(self):
        self.store.define_artifact(self.cid,self.a,ARTIFACT,'Unique',self.op())
        barrier=threading.Barrier(2)
        def register(_):
            store=Store(self.root/'data')
            try:
                barrier.wait(timeout=5)
                try: store.register_item(self.cid,self.a,'player:'+self.a,{},ARTIFACT,str(uuid.uuid4()));return True
                except Conflict:return False
            finally:store.close()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            result=list(pool.map(register,range(2)))
        self.assertEqual(sorted(result),[False,True])
    def test_capture_requires_cosave_and_valid_headers(self):
        self.ess.with_suffix('.skse').unlink()
        with self.assertRaises(FileNotFoundError): self.capture(self.a)
        self.ess.with_suffix('.skse').write_bytes(b'bad!')
        with self.assertRaises(Conflict): self.capture(self.a)
    def test_capture_profile_mismatch_rejected(self):
        (self.profile/'plugins.txt').write_text('*Skyrim.esm\n*Different.esp\n')
        with self.assertRaises(Conflict): self.capture(self.a)
    def test_save_changing_during_copy_never_publishes_snapshot(self):
        original=checkpoints.put_blob
        def copy(store,path):
            info=original(store,path)
            if Path(path)==self.ess:
                with self.ess.with_suffix('.skse').open('ab') as stream:stream.write(b'changed')
            return info
        with patch.object(checkpoints,'put_blob',copy):
            with self.assertRaises(Conflict):self.capture(self.a)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM snapshot').fetchone()[0],0)
    def test_symlink_source_is_rejected(self):
        link=self.root/'link.ess'
        try:
            link.symlink_to(self.ess)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows account cannot create test symlinks; no privileges are changed')
            raise
        with self.assertRaises(Conflict):checkpoints.file_identity(link)
    def test_non_regular_backup_source_is_rejected(self):
        with self.assertRaises(Conflict):checkpoints.file_identity(self.profile)
    def test_paired_checkpoint_requires_both_players_and_current_lineage(self):
        a=self.capture(self.a)
        with self.assertRaises(Conflict):checkpoints.checkpoint(self.store,self.cid,self.a,[a['id']],'bad',self.op())
        b=self.capture(self.b)
        checkpoint=checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'good',self.op())
        self.assertEqual(self.store.campaign(self.cid)['head'],checkpoint['id'])
        with self.assertRaises(Conflict):checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'stale',self.op())
    def test_snapshot_becomes_stale_after_campaign_mutation(self):
        a=self.capture(self.a);b=self.capture(self.b)
        self.present(self.a)
        with self.assertRaises(Conflict):checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'stale',self.op())
    def test_checkpoint_rejects_pending_transfers(self):
        item=self.item(); self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,self.op())
        a=self.capture(self.a);b=self.capture(self.b)
        with self.assertRaises(Conflict):checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'pending',self.op())
    def test_corrupt_blob_rejected(self):
        a=self.capture(self.a);b=self.capture(self.b)
        snapshot=self.store.one('SELECT * FROM snapshot WHERE id=?',(a['id'],))
        digest=json.loads(snapshot['files'])['save/character.ess']['sha256']
        checkpoints.blob_path(self.store,digest).write_bytes(b'corrupt')
        with self.assertRaises(Conflict):checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'bad',self.op())
    def test_export_preserves_original_files_and_domain_revision(self):
        before=(self.ess.read_bytes(),self.ess.with_suffix('.skse').read_bytes())
        pair=self.pair(); destination=self.root/'export'
        checkpoints.export_checkpoint(self.store,self.cid,pair['id'],destination)
        self.assertEqual(before,(self.ess.read_bytes(),self.ess.with_suffix('.skse').read_bytes()))
        self.assertEqual((destination/self.a/'save/character.ess').read_bytes(),before[0])
        report=json.loads((destination/'CHECKPOINT.json').read_text())
        self.assertEqual(json.loads(report['checkpoint']['state'])['campaign']['revision'],pair['revision'])
        self.assertFalse(report['game_integration'])
        with self.assertRaises(Conflict):checkpoints.export_checkpoint(self.store,self.cid,pair['id'],destination)
    def test_unsafe_export_path_in_snapshot_rejected(self):
        with self.assertRaises(Conflict):checkpoints._validate_files({'save/character.ess':{},'save/character.skse':{},'../../escape':{}})
    def test_unique_artifact_quantity_is_always_one(self):
        self.store.define_artifact(self.cid,self.a,ARTIFACT,'Unique',self.op())
        with self.assertRaises(Conflict):
            self.store.register_item(self.cid,self.a,'player:'+self.a,{'quantity':2},ARTIFACT,self.op())
        with self.assertRaises(Conflict):
            self.store.register_item(self.cid,self.a,'player:'+self.a,{'quantity':True},None,self.op())
    def test_runtime_fingerprint_hashes_actual_files_and_rejects_duplicate_names(self):
        value=checkpoints.runtime_fingerprint('test-build',['runtime='+str(self.ess)])
        self.assertEqual(value['files']['runtime']['sha256'],hashlib.sha256(self.ess.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            checkpoints.runtime_fingerprint('test-build',['runtime='+str(self.ess),'runtime='+str(self.ess)])
    def test_dismissed_follower_still_cannot_be_commanded_by_other_player(self):
        follower=self.follower()
        self.store.follower_state(self.cid,self.a,ACTOR,'dismissed',{},follower['version'],self.op())
        with self.assertRaises(Denied):self.store.permission(self.cid,self.b,ACTOR,'command')
    def test_quest_classification_change_revokes_old_service_grant(self):
        self.store.set_npc_rule(self.cid,self.a,ACTOR,'service',self.op())
        grant=self.store.acquire_dialogue(self.cid,self.b,ACTOR)
        self.store.set_npc_rule(self.cid,self.a,ACTOR,'quest',self.op())
        with self.assertRaises(Denied):self.store.check_dialogue(self.cid,self.b,ACTOR,grant['token'],grant['generation'])
    def test_checkpoint_replay_does_not_create_second_checkpoint(self):
        a=self.capture(self.a);b=self.capture(self.b);op=self.op()
        first=checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'same',op)
        second=checkpoints.checkpoint(self.store,self.cid,self.a,[a['id'],b['id']],'same',op)
        self.assertEqual(first,second)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM checkpoint').fetchone()[0],1)

    def test_api_credential_scope_and_explicit_integration_status(self):
        server=Server(self.root/'data',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            health=json.load(urllib.request.urlopen(url+'/health'))
            self.assertFalse(health['game_integration'])
            me=urllib.request.Request(url+'/v1/me',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+self.p1['token']})
            identity=json.load(urllib.request.urlopen(me))
            self.assertEqual(identity['player'],self.a)
            self.assertTrue(identity['is_leader'])
            def request(token,origin=None):
                headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
                if origin:headers['Origin']=origin
                return urllib.request.urlopen(urllib.request.Request(url+'/v1/state',data=json.dumps({'campaign':'forged'}).encode(),headers=headers))
            data=json.load(request(self.p2['token']))
            self.assertEqual(data['id'],self.cid)
            self.assertNotIn('token_hash',data['players'][0])
            with self.assertRaises(urllib.error.HTTPError) as error:request('wrong')
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as error:request(self.p2['token'],'http://bad.example')
            self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
