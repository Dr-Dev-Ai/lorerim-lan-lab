import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from installer import install_worker as w

class GuidedInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def test_rejects_download_corruption_without_replacing_cache(self):
        file=self.base/'cached.zip';file.write_bytes(b'old-cache')
        response=io.BytesIO(b'corrupt');response.headers={}
        with patch.object(w.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'integrity check'):
                w.download('https://example.invalid/file','0'*64,file,'Test')
        self.assertEqual(file.read_bytes(),b'old-cache')
        self.assertFalse(file.with_suffix('.zip.download').exists())

    def test_rejects_archive_escape_before_extracting_any_files(self):
        archive=self.base/'release.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('safe.txt','safe');z.writestr('../escape.txt','unsafe')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            w.extract_zip(archive,self.base/'extracted')
        self.assertFalse((self.base/'escape.txt').exists())
        self.assertFalse((self.base/'extracted/safe.txt').exists())

    @unittest.skipUnless(os.name=='nt','Native Windows copy test')
    def test_physical_copy_resumes_and_excludes_downloads_and_old_saves(self):
        source=self.base/'source';lab=self.base/'lab'
        for name,content in [('mods/Mod/example.txt','original'),('profiles/Normal/modlist.txt','+Mod'),
                             ('profiles/Normal/saves/old.ess','private-save'),('downloads/large.zip','cache')]:
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
        w.copy_lab(source,lab,self.base/'copy.log')
        self.assertEqual((lab/'mods/Mod/example.txt').read_text(),'original')
        self.assertFalse((lab/'downloads/large.zip').exists())
        self.assertFalse((lab/'profiles/Normal/saves/old.ess').exists())
        (lab/'mods/Mod/example.txt').unlink()
        w.copy_lab(source,lab,self.base/'copy.log')
        self.assertEqual((lab/'mods/Mod/example.txt').read_text(),'original')
        self.assertEqual((source/'profiles/Normal/saves/old.ess').read_text(),'private-save')
        self.assertEqual((source/'mods/Mod/example.txt').stat().st_nlink,1)

    def test_failed_configuration_is_retained_and_original_ini_restored(self):
        lab=self.base/'lab';lab.mkdir();(lab/'ModOrganizer.ini').write_text('original')
        w.recover_configuration(lab)
        (lab/'ModOrganizer.ini').write_text('partly-modified')
        for p in (lab/'profiles'/w.prepare_lab.PROFILE,lab/'mods'/w.prepare_lab.MOD,self.base/'server'):
            p.mkdir(parents=True);(p/'evidence.txt').write_text(p.name)
        w.recover_configuration(lab)
        self.assertEqual((lab/'ModOrganizer.ini').read_text(),'original')
        self.assertEqual(len(list((lab/'installer-recovery').rglob('evidence.txt'))),3)
        self.assertFalse((self.base/'server').exists())

    def test_overlapping_install_paths_are_rejected(self):
        with self.assertRaises(ValueError):w.separate(self.base,self.base/'child')
        with self.assertRaises(ValueError):w.separate(self.base,self.base)

    def test_download_failure_never_starts_large_copy(self):
        source=self.base/'source';source.mkdir();lab=self.base/'install/lab'
        statefile=lab.parent/'state.json'
        with patch.object(w,'preflight',return_value=(source,lab,statefile,None,'Ultra',3490)), \
             patch.object(w,'source_size',return_value=1), \
             patch.object(w,'download',side_effect=OSError('offline')), \
             patch.object(w,'copy_lab') as copy:
            with self.assertRaisesRegex(OSError,'offline'):w.run(source,lab,'10.0.0.250')
            copy.assert_not_called()
        self.assertFalse(lab.exists())

    def test_fix_failure_cannot_create_play_shortcut_or_complete_marker(self):
        source=self.base/'source';source.mkdir();lab=self.base/'install/lab';lab.mkdir(parents=True)
        statefile=lab.parent/'state.json'
        state={'format':1,'source':str(source),'lab':str(lab),'copied':True,'configured':True}
        with patch.object(w,'preflight',return_value=(source,lab,statefile,state,'Ultra',3490)), \
             patch.object(w,'download',return_value=self.base/'download'), \
             patch.object(w,'extract_zip'),patch.object(w.subprocess,'run'), \
             patch.object(w.camera_fix,'apply',side_effect=ValueError('unsupported')), \
             patch.object(w,'verify') as verify,patch.object(w,'shortcuts') as shortcut:
            with self.assertRaisesRegex(ValueError,'unsupported'):w.run(source,lab,'10.0.0.250')
            shortcut.assert_not_called();verify.assert_not_called()
        self.assertNotIn('complete',state)

    def test_completed_pipeline_applies_every_fix_before_verify_and_shortcut(self):
        source=self.base/'source';source.mkdir();lab=self.base/'install/lab';lab.mkdir(parents=True)
        statefile=lab.parent/'state.json'
        state={'format':1,'source':str(source),'lab':str(lab),'copied':True,'configured':True}
        order=[]
        with patch.object(w,'preflight',return_value=(source,lab,statefile,state,'Ultra',3490)), \
             patch.object(w,'download',return_value=self.base/'download'), \
             patch.object(w,'extract_zip'),patch.object(w.subprocess,'run'), \
             patch.object(w.camera_fix,'apply',side_effect=lambda *a:order.append('camera')), \
             patch.object(w.bsa_guard_fix,'apply',side_effect=lambda *a:order.append('bsa')), \
             patch.object(w.camera_fix,'apply_exact',side_effect=lambda lab,dll,*a:order.append(dll.name)), \
             patch.object(w.jcontainers_update,'install',side_effect=lambda *a:order.append('jcontainers')), \
             patch.object(w,'verify',side_effect=lambda *a:order.append('verify')), \
             patch.object(w,'shortcuts',side_effect=lambda *a:order.append('shortcut')):
            w.run(source,lab,'10.0.0.250')
        self.assertEqual(order,['camera','bsa','PlayerEyesBlinkFix.dll','BetterAltTab.dll','SkyrimTogether.exe','jcontainers','verify','shortcut'])
        self.assertTrue(json.loads(statefile.read_text())['complete'])

if __name__=='__main__':unittest.main()
