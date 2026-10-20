import copy
import json
from pathlib import Path
import tempfile
import unittest
import lancheck as lc


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        def put(name, data):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)
        self.put = put
        put('profiles/Test/modlist.txt', '+High\n+Low\n-Disabled\n')
        put('profiles/Test/plugins.txt', '*Test.esp\n')
        masters = ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm']
        put('profiles/Test/loadorder.txt', '\n'.join(masters + ['Test.esp']) + '\n')
        for name in masters:
            put('Stock Game/Data/' + name, name)
        put('mods/High/Test.esp', 'winning-plugin')
        put('mods/Low/test.esp', 'losing-plugin')
        put('mods/High/SKSE/Plugins/test.dll', 'native-v1')
        put('mods/High/Meshes/Actors/behavior.hkx', 'generated-v1')
        put('mods/High/Textures/test.dds', 'texture')
        put('mods/High/archive.bsa', 'opaque-archive')
        put('mods/High/hidden.esp.mohidden', 'hidden')
        put('Stock Game/SkyrimSE.exe', 'runtime')
        put('Stock Game/engine.dll', 'stock-loader')
        put('mods/High/Root/engine.dll', 'root-builder-loader')

    def test_priority_root_builder_and_hidden(self):
        a = lc.audit(self.root, 'Test', True)
        self.assertEqual(a['files']['data/test.esp']['source'], 'High')
        self.assertEqual(a['files']['root/engine.dll']['source'], 'High')
        self.assertFalse(any(k.endswith('.mohidden') for k in a['files']))
        self.put('overwrite/test.esp', 'overwrite-winner')
        self.assertEqual(lc.audit(self.root, 'Test', True)['files']['data/test.esp']['source'], 'overwrite')

    def test_incomplete_cannot_pass(self):
        a = lc.audit(self.root, 'Test')
        with self.assertRaises(ValueError):
            lc.compare(a, a)

    def test_identical_content_portable_roots(self):
        a = lc.audit(self.root, 'Test', True)
        b = copy.deepcopy(a)
        b['root'] = 'D:/Guest'
        self.assertEqual(lc.compare(a, b), [])

    def test_native_generated_archive_and_runtime_changes(self):
        a = lc.audit(self.root, 'Test', True)
        for key in ['data/skse/plugins/test.dll', 'data/meshes/actors/behavior.hkx', 'data/archive.bsa', 'root/skyrimse.exe']:
            b = copy.deepcopy(a)
            b['files'][key]['sha256'] = 'changed'
            self.assertEqual(lc.compare(a, b)[0]['file'], key)

    def test_missing_file_and_order_detected(self):
        a = lc.audit(self.root, 'Test', True)
        b = copy.deepcopy(a)
        del b['files']['data/test.esp']
        b['enabled_mods'].reverse()
        self.assertEqual(len(lc.compare(a, b)), 2)

    def test_missing_mod_and_plugin_fail_closed(self):
        self.put('profiles/Test/plugins.txt', '*Missing.esp')
        with self.assertRaisesRegex(ValueError, 'absent from loadorder'):
            lc.audit(self.root, 'Test')
        self.put('profiles/Test/modlist.txt', '+Missing')
        with self.assertRaisesRegex(ValueError, 'mod missing'):
            lc.audit(self.root, 'Test')

    def test_metrics_are_from_input(self):
        self.put('samples.csv', 'metric,unit,value\nrtt,ms,2\nrtt,ms,4\n')
        r = lc.metrics(self.root / 'samples.csv')[0]
        self.assertEqual((r['count'], r['mean'], r['p95']), (2, 3, 4))

if __name__ == '__main__':
    unittest.main(verbosity=2)
