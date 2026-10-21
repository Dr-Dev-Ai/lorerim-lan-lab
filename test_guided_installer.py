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

    def test_assets_are_linked_but_fix_targets_settings_and_generated_files_are_private(self):
        source=self.base/'source';lab=self.base/'lab'
        assets=['mods/Art/textures/large.dds','mods/Art/main.bsa','Stock Game/Data/Skyrim.bsa']
        private=['mods/Native/SKSE/Plugins/plugin.dll','mods/Native/SKSE/Plugins/plugin.ini',
                 'mods/Scripts/example.pex','mods/Records/example.esp','ModOrganizer.ini',
                 'overwrite/generated.dds','Stock Game/screenshot.png','mods/Art/Root/palette.dds']
        for name in assets+private:
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'original')
        result=w.link_lab(source,lab,self.base/'links.json')
        self.assertEqual(result['shared_files'],len(assets))
        self.assertEqual(result['private_files'],len(private))
        for name in assets:self.assertTrue(os.path.samefile(source/name,lab/name),name)
        for name in private:
            self.assertFalse(os.path.samefile(source/name,lab/name),name)
            (lab/name).write_bytes(b'changed independently')
            self.assertEqual((source/name).read_bytes(),b'original')
        w.link_lab(source,lab,self.base/'links.json')
        for name in assets:self.assertEqual((source/name).stat().st_nlink,2)

    def test_old_partial_physical_copy_becomes_link_without_changing_source(self):
        source=self.base/'source';lab=self.base/'lab'
        asset=Path('mods/Art/archive.bsa');(source/asset).parent.mkdir(parents=True)
        (source/asset).write_bytes(b'complete source asset')
        (lab/asset).parent.mkdir(parents=True);(lab/asset).write_bytes(b'partial copy')
        w.link_lab(source,lab,self.base/'links.json')
        self.assertTrue(os.path.samefile(source/asset,lab/asset))
        self.assertEqual((source/asset).read_bytes(),b'complete source asset')

    def test_space_estimate_ignores_large_shared_asset_bytes(self):
        source=self.base/'source';(source/'mods/Art').mkdir(parents=True)
        with (source/'mods/Art/huge.bsa').open('wb') as f:f.truncate(128*1024*1024)
        (source/'ModOrganizer.ini').write_bytes(b'small settings')
        self.assertLess(w.private_size(source),1024*1024)

    def test_unsupported_hard_links_do_not_fall_back_to_bulk_copy(self):
        source=self.base/'source';lab=self.base/'lab'
        asset=source/'mods/Art/a.dds';asset.parent.mkdir(parents=True);asset.write_bytes(b'asset')
        with patch.object(w.os,'link',side_effect=OSError('not supported')),patch.object(w.shutil,'copy2') as copying:
            with self.assertRaisesRegex(ValueError,'same local drive'):w.link_lab(source,lab,self.base/'links.json')
            copying.assert_not_called()
        self.assertEqual(asset.read_bytes(),b'asset')

    def test_same_volume_requirement_prevents_cross_drive_copy(self):
        source=self.base/'source';source.mkdir();lab=self.base/'lab'
        with patch.object(w,'same_volume',side_effect=ValueError('SAME drive')),patch.object(w.shutil,'copy2') as copying:
            with self.assertRaisesRegex(ValueError,'SAME drive'):w.link_lab(source,lab,self.base/'links.json')
            copying.assert_not_called()
        self.assertFalse(lab.exists())

    def test_unexpected_destination_hard_link_is_not_overwritten(self):
        source=self.base/'source';lab=self.base/'lab'
        asset=source/'mods/Art/a.dds';asset.parent.mkdir(parents=True);asset.write_bytes(b'expected')
        unrelated=self.base/'other.dds';unrelated.write_bytes(b'unrelated')
        target=lab/'mods/Art/a.dds';target.parent.mkdir(parents=True);os.link(unrelated,target)
        with self.assertRaisesRegex(ValueError,'Unexpected shared destination'):
            w.link_lab(source,lab,self.base/'links.json')
        self.assertEqual(unrelated.read_bytes(),b'unrelated')

    def test_overlapping_install_paths_are_rejected(self):
        with self.assertRaises(ValueError):w.separate(self.base,self.base/'child')
        with self.assertRaises(ValueError):w.separate(self.base,self.base)

    def test_download_failure_never_starts_large_copy(self):
        source=self.base/'source';source.mkdir();lab=self.base/'install/lab'
        statefile=lab.parent/'state.json'
        with patch.object(w,'preflight',return_value=(source,lab,statefile,None,'Ultra',3490)), \
             patch.object(w,'private_size',return_value=1), \
             patch.object(w,'download',side_effect=OSError('offline')), \
             patch.object(w,'link_lab') as copy:
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
