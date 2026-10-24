import hashlib
import json
import struct
import tempfile
import unittest
import uuid
from pathlib import Path
from campaign_manager.store import Store,Conflict,Denied
from campaign_manager import checkpoints,cosave,admission


def fixture_cosave(identity,other=b'other-plugin-data'):
    payload=cosave.encode_record(identity)
    chunk=struct.pack('<III',cosave.RECORD_ID,1,len(payload))+payload
    return (struct.pack('<4sIIII',b'SKSE',1,0x20206,0x1064920,2)
        +struct.pack('<III',0xABCDEF01,1,12+len(other))+struct.pack('<III',0x12345678,2,len(other))+other
        +struct.pack('<III',cosave.PLUGIN_ID,1,len(chunk))+chunk)

class NativeIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'data');self.profile=self.root/'profile';self.profile.mkdir()
        (self.profile/'plugins.txt').write_text('*Skyrim.esm\n');(self.profile/'modlist.txt').write_text('+Fixture\n')
        self.runtime={'fixture':True};self.cid=self.store.create_campaign('Native test',checkpoints.profile_manifest(self.profile,self.runtime))['id']
        self.a=self.store.add_player(self.cid,'Leader',True)['player'];self.b=self.store.add_player(self.cid,'Partner')['player']
        self.epoch=self.store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(self.cid,))['epoch']
        self.identity={'version':1,'character':str(uuid.uuid4()),'campaign':self.cid,'epoch':self.epoch,'checkpoint':'','revision':self.store.campaign(self.cid)['revision']}
        self.ess=self.root/'fixture.ess';self.ess.write_bytes(b'TESV_SAVEGAMEfixture')
        self.skse=self.ess.with_suffix('.skse');self.skse.write_bytes(fixture_cosave(self.identity))
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def capture(self,pid):
        return checkpoints.capture(self.store,self.cid,pid,self.ess,self.profile,self.runtime,str(uuid.uuid4()),settle_seconds=.1)
    def enroll(self):
        snapshot=self.capture(self.a);admission.enroll_snapshot(self.store,self.cid,self.a,snapshot['id']);return snapshot
    def proof(self):
        return dict(self.identity,ess_sha256=checkpoints.sha_file(self.ess),skse_sha256=checkpoints.sha_file(self.skse))
    def test_identity_roundtrip_and_foreign_chunks(self):
        self.assertEqual(cosave.read_identity(self.skse),self.identity)
        self.assertEqual(len(cosave.encode_record(self.identity)),160)
    def test_truncation_and_duplicate_identity_are_rejected(self):
        original=self.skse.read_bytes()
        for cut in (0,4,19,31,len(original)-1):
            self.skse.write_bytes(original[:cut])
            with self.assertRaises(Conflict):cosave.read_identity(self.skse)
        chunk=struct.pack('<III',cosave.RECORD_ID,1,160)+cosave.encode_record(self.identity)
        self.skse.write_bytes(struct.pack('<4sIIII',b'SKSE',1,0,0,1)+struct.pack('<III',cosave.PLUGIN_ID,2,2*len(chunk))+chunk*2)
        with self.assertRaises(Conflict):cosave.read_identity(self.skse)
    def test_record_canonical_validation(self):
        value=cosave.encode_record(self.identity)
        with self.assertRaises(Conflict):cosave.decode_record(value[:-1])
        with self.assertRaises(Conflict):cosave.decode_record(struct.pack('<I',2)+value[4:])
        with self.assertRaises(ValueError):cosave.encode_record(dict(self.identity,character=self.identity['character'].upper()))
    def test_rebranch_changes_only_owned_payload(self):
        target=self.root/'new.skse';epoch=str(uuid.uuid4());head=str(uuid.uuid4())
        before=self.skse.read_bytes();location=cosave.locate(self.skse)['offset']
        changed=cosave.rebranch(self.skse,target,epoch,head,17)
        after=target.read_bytes()
        self.assertEqual(before[:location],after[:location]);self.assertEqual(before[location+160:],after[location+160:])
        self.assertEqual(changed['character'],self.identity['character']);self.assertEqual(changed['epoch'],epoch)
        self.assertEqual(self.skse.read_bytes(),before)
        with self.assertRaises(FileExistsError):cosave.rebranch(self.skse,target,epoch,head,17)
        self.assertEqual(target.read_bytes(),after)
    def test_enrolled_pair_admits_and_wrong_character_or_epoch_denied(self):
        self.enroll();proof=self.proof()
        self.assertTrue(admission.check(self.store,self.cid,self.a,proof)['allowed'])
        for key in ('character','campaign','epoch'):
            with self.assertRaises(Denied):admission.check(self.store,self.cid,self.a,dict(proof,**{key:str(uuid.uuid4())}))
        for key in ('ess_sha256','skse_sha256'):
            with self.assertRaises(Denied):admission.check(self.store,self.cid,self.a,dict(proof,**{key:'0'*64}))
    def test_character_cannot_be_claimed_by_second_player(self):
        self.enroll();second=self.capture(self.b)
        with self.assertRaises(Denied):admission.enroll_snapshot(self.store,self.cid,self.b,second['id'])
    def test_presence_and_restart_preserve_enrollment(self):
        self.enroll();proof=self.proof()
        self.store.session(self.cid,self.a,'native-test-session-0001','open',proof)
        self.store.session(self.cid,self.a,'native-test-session-0001','close')
        self.store.close();self.store=Store(self.root/'data')
        self.assertTrue(admission.check(self.store,self.cid,self.a,proof)['allowed'])
    def test_pending_transfer_blocks_admission(self):
        self.enroll()
        item=self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,str(uuid.uuid4()))
        self.store.prepare_transfer(self.cid,self.a,item['id'],'player:'+self.b,1,str(uuid.uuid4()))
        with self.assertRaises(Conflict):admission.check(self.store,self.cid,self.a,self.proof())
    def test_enrollment_rejects_cross_campaign_and_stale_checkpoint(self):
        self.skse.write_bytes(fixture_cosave(dict(self.identity,campaign=str(uuid.uuid4()))))
        capture=self.capture(self.a)
        with self.assertRaises(Conflict):admission.enroll_snapshot(self.store,self.cid,self.a,capture['id'])

    def test_recovery_rebranches_only_owned_identity_and_preserves_characters(self):
        from campaign_manager.recovery import prepare_recovery
        first=self.enroll()
        other=dict(self.identity,character=str(uuid.uuid4()))
        self.skse.write_bytes(fixture_cosave(other))
        second=self.capture(self.b);admission.enroll_snapshot(self.store,self.cid,self.b,second['id'])
        cp=checkpoints.checkpoint(self.store,self.cid,self.a,[first['id'],second['id']],'Managed checkpoint',str(uuid.uuid4()))
        destination=self.root/'recovered'
        prepare_recovery(self.store,self.cid,self.a,cp['id'],destination)
        recovered=Store(destination/'data')
        try:
            new_epoch=recovered.one('SELECT epoch FROM native_epoch WHERE campaign=?',(self.cid,))['epoch']
            self.assertNotEqual(new_epoch,self.epoch)
            for pid,old in ((self.a,self.identity),(self.b,other)):
                ess=destination/'players'/pid/'save/character.ess';skse=ess.with_suffix('.skse')
                identity=cosave.read_identity(skse)
                self.assertEqual(identity['character'],old['character'])
                self.assertEqual(identity['epoch'],new_epoch)
                proof=dict(identity,ess_sha256=checkpoints.sha_file(ess),skse_sha256=checkpoints.sha_file(skse))
                self.assertTrue(admission.check(recovered,self.cid,pid,proof)['allowed'])
                with self.assertRaises(Denied):admission.check(recovered,self.cid,pid,dict(proof,epoch=self.epoch))
        finally:recovered.close()

    def test_committed_domain_changes_require_new_paired_save(self):
        self.enroll()
        self.store.register_item(self.cid,self.a,'player:'+self.a,{},None,str(uuid.uuid4()))
        with self.assertRaises(Conflict):admission.check(self.store,self.cid,self.a,self.proof())

    def test_world_mutation_marker_is_durable_and_idempotent(self):
        self.enroll();operation=str(uuid.uuid4())
        first=self.store.mark_native_world_changed(self.cid,self.a,operation)
        revision=self.store.campaign(self.cid)['revision']
        self.assertEqual(first,self.store.mark_native_world_changed(self.cid,self.a,operation))
        self.assertEqual(revision,self.store.campaign(self.cid)['revision'])
        self.store.close();self.store=Store(self.root/'data')
        with self.assertRaises(Conflict):admission.check(self.store,self.cid,self.a,self.proof())

    def test_presence_and_existing_alias_reports_do_not_stale_enrolled_world(self):
        self.enroll()
        self.store.session(self.cid,self.a,'presence-bookkeeping-0001','open',self.proof())
        revision=self.store.campaign(self.cid)['revision']
        self.store.observe_follower(self.cid,self.a,'Skyrim.esm|00A2C94','seen',str(uuid.uuid4()))
        self.assertEqual(revision,self.store.campaign(self.cid)['revision'])
        self.store.session(self.cid,self.a,'presence-bookkeeping-0001','close')
        self.assertTrue(admission.check(self.store,self.cid,self.a,self.proof())['allowed'])

    def test_stale_native_header_revision_cannot_be_enrolled(self):
        self.skse.write_bytes(fixture_cosave(dict(self.identity,revision=0)))
        snapshot=self.capture(self.a)
        with self.assertRaises(Conflict):admission.enroll_snapshot(self.store,self.cid,self.a,snapshot['id'])
