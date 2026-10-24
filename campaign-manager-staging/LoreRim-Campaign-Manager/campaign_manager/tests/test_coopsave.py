import base64
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from campaign_manager import coopsave,admission,checkpoints,cosave
from campaign_manager.store import Store,Conflict,Denied
from test_native_identity import fixture_cosave

class CoopSaveTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root/'data')
        self.profile=self.root/'profile';self.profile.mkdir()
        (self.profile/'plugins.txt').write_text('*Skyrim.esm\n');(self.profile/'modlist.txt').write_text('+Test\n')
        self.runtime={'test_fixture':True};self.cid=self.store.create_campaign('Co-op',checkpoints.profile_manifest(self.profile,self.runtime))['id']
        self.a=self.store.add_player(self.cid,'Leader',True)['player'];self.b=self.store.add_player(self.cid,'Partner')['player']
        self.epoch=self.store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(self.cid,))['epoch'];self.identities={}
        for pid in (self.a,self.b):
            identity={'version':1,'character':str(uuid.uuid4()),'campaign':self.cid,'epoch':self.epoch,'checkpoint':'','revision':self.store.campaign(self.cid)['revision']}
            self.identities[pid]=identity
            save=self.root/(pid+'.ess');save.write_bytes(b'TESV_SAVEGAMEfixture');save.with_suffix('.skse').write_bytes(fixture_cosave(identity))
            admission.capture_native(self.store,self.cid,pid,save,self.profile,self.runtime,str(uuid.uuid4()),settle_seconds=.1)
            self.store.set_presence(self.cid,pid,True,str(uuid.uuid4()))
        self.hashes={name:checkpoints.sha_file(self.profile/name) for name in ('plugins.txt','modlist.txt')}
    def tearDown(self):self.store.close();self.temp.cleanup()
    def prepare(self):return coopsave.request(self.store,self.cid,self.a,'Together',str(uuid.uuid4()))['id']
    def seal(self,proposal):
        for pid in (self.a,self.b):coopsave.ready(self.store,self.cid,pid,proposal,self.hashes)
        return coopsave.seal(self.store,self.cid,self.a,proposal)
    def payloads(self,proposal,pid):
        row=coopsave.status(self.store,self.cid,pid,proposal)
        identity=dict(self.identities[pid],checkpoint=proposal,revision=row['revision'])
        return {'ess':b'TESV_SAVEGAME'+pid.encode()+b'updated-world-state'*100,
                'skse':fixture_cosave(identity)}
    def send(self,proposal,pid,kind,data):
        digest=hashlib.sha256(data).hexdigest()
        for offset in range(0,len(data),127):
            result=coopsave.upload(self.store,self.cid,pid,proposal,kind,offset,len(data),digest,base64.b64encode(data[offset:offset+127]).decode())
        self.assertTrue(result['verified'])
    def test_two_complete_pairs_commit_atomically_and_admit_after_restart(self):
        proposal=self.prepare();self.seal(proposal)
        payloads={pid:self.payloads(proposal,pid) for pid in (self.a,self.b)}
        for pid,files in payloads.items():
            for kind,data in files.items():self.send(proposal,pid,kind,data)
        result=coopsave.commit(self.store,self.cid,self.a,proposal)
        self.assertEqual(result['checkpoint'],proposal)
        self.assertEqual(self.store.campaign(self.cid)['head'],proposal)
        self.assertEqual(coopsave.commit(self.store,self.cid,self.a,proposal)['checkpoint'],proposal)
        self.store.close();self.store=Store(self.root/'data')
        for pid,files in payloads.items():
            proof=dict(self.identities[pid],checkpoint=proposal,ess_sha256=hashlib.sha256(files['ess']).hexdigest(),skse_sha256=hashlib.sha256(files['skse']).hexdigest())
            self.assertTrue(admission.check(self.store,self.cid,pid,proof)['allowed'])
    def test_missing_participant_or_pair_never_moves_campaign_head(self):
        proposal=self.prepare();coopsave.ready(self.store,self.cid,self.a,proposal,self.hashes)
        with self.assertRaises(Conflict):coopsave.seal(self.store,self.cid,self.a,proposal)
        coopsave.ready(self.store,self.cid,self.b,proposal,self.hashes);coopsave.seal(self.store,self.cid,self.a,proposal)
        for kind,data in self.payloads(proposal,self.a).items():self.send(proposal,self.a,kind,data)
        with self.assertRaises(Conflict):coopsave.commit(self.store,self.cid,self.a,proposal)
        self.assertIsNone(self.store.campaign(self.cid)['head'])
    def test_sealing_blocks_domain_changes_and_abort_releases_it(self):
        proposal=self.prepare();self.seal(proposal)
        with self.assertRaises(Conflict):self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,str(uuid.uuid4()))
        coopsave.abort(self.store,self.cid,self.b,proposal,'Client could not pause')
        self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,str(uuid.uuid4()))
        self.assertIsNone(self.store.campaign(self.cid)['head'])
    def test_upload_replay_and_append_before_journal_commit_recover_without_duplication(self):
        proposal=self.prepare();self.seal(proposal)
        data=self.payloads(proposal,self.a)['ess'];digest=hashlib.sha256(data).hexdigest();chunk=data[:127]
        result=coopsave.upload(self.store,self.cid,self.a,proposal,'ess',0,len(data),digest,base64.b64encode(chunk).decode())
        again=coopsave.upload(self.store,self.cid,self.a,proposal,'ess',0,len(data),digest,base64.b64encode(chunk).decode())
        self.assertEqual(again['received'],result['received'])
        path=coopsave._path(self.store,proposal,self.a,'ess')
        with path.open('ab') as stream:stream.write(data[127:254])
        recovered=coopsave.upload(self.store,self.cid,self.a,proposal,'ess',127,len(data),digest,base64.b64encode(data[127:254]).decode())
        self.assertEqual(recovered['received'],254);self.assertEqual(path.read_bytes(),data[:254])
        with self.assertRaises(Conflict):coopsave.upload(self.store,self.cid,self.a,proposal,'ess',0,len(data),digest,base64.b64encode(b'x'*127).decode())
    def test_wrong_epoch_or_profile_is_rejected_and_other_player_cannot_seal(self):
        proposal=self.prepare()
        with self.assertRaises(Conflict):coopsave.ready(self.store,self.cid,self.a,proposal,dict(self.hashes,**{'plugins.txt':'0'*64}))
        self.seal(proposal)
        with self.assertRaises(Denied):coopsave.seal(self.store,self.cid,self.b,proposal)
        bad=fixture_cosave(dict(self.identities[self.a],checkpoint=proposal,epoch=str(uuid.uuid4())))
        with self.assertRaises(Conflict):self.send(proposal,self.a,'skse',bad)
        self.assertIsNone(self.store.campaign(self.cid)['head'])
    def test_unfinished_checkpoint_blocks_admission_and_expiry_preserves_previous_head(self):
        proposal=self.prepare()
        self.store.db.execute('UPDATE coop_request SET expires=0 WHERE id=?',(proposal,))
        self.assertEqual(coopsave.expire(self.store),1)
        self.assertEqual(coopsave.status(self.store,self.cid,self.a,proposal)['state'],'aborted')
        self.assertIsNone(self.store.campaign(self.cid)['head'])
