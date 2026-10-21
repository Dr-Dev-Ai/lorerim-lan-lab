"""Install the verified upstream Lua memory fix into a marked isolated lab."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

URL = 'https://github.com/ryobg/JContainers/releases/download/v4.2.13.1/JContainers64-v4.2.13.1.7z'
ARCHIVE_SHA256 = '2edd555821e70d94784c79b9a80a34d235f682d4d69f956f28e0411fd43a020a'
FILES = {'scripts/JArray.pex': ('9617c2bcdc90d4a23af500c7f4bb68663b13c9775bd9a7724f21e6d5ccfa2c0b', 'c2ef66f3556cb45303266e29fe258f5ff455da1ca902c2104302e40df6391934'), 'scripts/JAtomic.pex': ('01d2a9a95665feb236389cc8cc0a7a574e810c64bf7b81c2cde1bada23a0b6d3', 'ba5296e19c34ac92d3316f7530887127dd189faab953009b47725314cd44adf1'), 'scripts/JContainers.pex': ('fc554b6cccbc94a1f5100b92930ddb7780f3b55325d90f9b6f4653666f3978b4', '2699e8cd0eba3a083453b29fbbcb6399c2401a076eba34c469229f5f6196f8ba'), 'scripts/JContainers_DomainExample.pex': ('9663b83c2461b500ed928b194203d04f338b0a44b36bfbb1e63582f64cf3b9c4', '0eb30b23424ce128b2769d9e352dac775e2ae782aada41aa4d359f6a78e6890b'), 'scripts/JDB.pex': ('5b8177e4a675cd6a578df8cd5353bf785cd5b2f35992258a0e62b46974ff75de', 'f9957f81a4be0be19268191ec9f8104ab36a5b0fdd8be1038df1498e659c6c98'), 'scripts/JFormDB.pex': ('43ecfdb2766213a3873b4cdb0bb22b5178f062d8d20451d0c248d680059b0e99', 'bd3a4e13b855be3eecf82bd250d510f0e0a9ad3de3bec3f63ce07439d46a321c'), 'scripts/JFormMap.pex': ('53f8f4c26cd7b48fe0440e309a9f8ef94798b45d377842d6a28e0506091907c5', '28b7f0a1c67a3f92cad4af84b58786a470e862a66e9ba0a494c5a53556ab8ebf'), 'scripts/JIntMap.pex': ('e35a1cd1834e911a7024a451ec1d70244915e8e3b26966551cf3a383a4edf2a4', '9e3cd88bb7cb28877b5b98a0ed5b132b6cd765161a2d988e5f951aafd35ea49e'), 'scripts/JLua.pex': ('f7b528592c09b98ddeda051e362748cd7738ac2cb7407b4ace7ad31547078c43', 'ae5e9552d09e3506e33922d347796d5dddd7b7015c8db7ed2aaab627046a05a3'), 'scripts/JMap.pex': ('28bd24cfffde3b3044b131b0fb0e110ca2bcbcc0d2926a9ca2261cc9f318bbe9', '29a6f277e139e1ae4e88032a5a996c7eacb521d6bbcf8a3d6dc219abcd88208d'), 'scripts/JString.pex': ('9fee17d0fd7e0afcbc755c574cbac901a2b1a8aca648e3a77ef601c600ab2cdc', '1fcbba2de1bb4f8f5b0af31100d9f27654870b67eee6d6df82086e4dd96eecbc'), 'scripts/JValue.pex': ('939af17b08ae34fc7a6c62b5a6f29e96f7f24406c7682b9b65a469de4dbbf8ae', '67c99cb64585c82575150b09429d2edd9cd1b291815cdaedf52df2d03a03ded4'), 'scripts/source/JArray.psc': ('864f35661bf426a2bc934a912f878fb57e09d0ce1eaa98933f03c71328d8c791', '864f35661bf426a2bc934a912f878fb57e09d0ce1eaa98933f03c71328d8c791'), 'scripts/source/JAtomic.psc': ('2a56f99a0588b99b41b195e54bc9711f966166c5da81d9255cc4474f04027a63', '2a56f99a0588b99b41b195e54bc9711f966166c5da81d9255cc4474f04027a63'), 'scripts/source/JContainers.psc': ('a59a44265e12fc3e1906c5f8bf835b456087bb707e09d2d540861dfcdabc9e2f', 'a59a44265e12fc3e1906c5f8bf835b456087bb707e09d2d540861dfcdabc9e2f'), 'scripts/source/JContainers_DomainExample.psc': ('472462c10a183ef39150a8b6a0cf8adf41c4b17505a759557c96c2b2642ff3e1', '42f943baf1f0bab600b2ef0d3b6e96b8f95811ab708347b4a65395ff0a71a1ef'), 'scripts/source/JDB.psc': ('ea25762f51a998617481e352552c70ab574188c1e4c28a6b48aa8bc0570b2a4f', 'ea25762f51a998617481e352552c70ab574188c1e4c28a6b48aa8bc0570b2a4f'), 'scripts/source/JFormDB.psc': ('9f0ac3a20b7c377f92f98b34c1e836197c0a22043e7438cd5c3b38a0c2e9f8ff', '9f0ac3a20b7c377f92f98b34c1e836197c0a22043e7438cd5c3b38a0c2e9f8ff'), 'scripts/source/JFormMap.psc': ('add4f4e124f99c14f6764b33e9ba93e352bf14e410ec523ab5523915ad92a4db', 'bbce95662d45f1425daeb4096cce2fb7cd8ee4b1befa92997c85909ba0507188'), 'scripts/source/JIntMap.psc': ('3ead5fd4d62016a6d9489a1d839d96668d823aa49569f0ad2567cba5b209c1ea', '4db85aad900e2a377131cd93e72ccedd5d7f0d4c22d18457f3f3926d69184e62'), 'scripts/source/JLua.psc': ('a8f37d86ef5d9851a30dd13e0b109af6e1aff31e484d35992c6ed88ab69ef638', 'a8f37d86ef5d9851a30dd13e0b109af6e1aff31e484d35992c6ed88ab69ef638'), 'scripts/source/JMap.psc': ('06532036b8e8a5bb0d760fbaaace23c2e7fc74b69901bd27dab40cc35087405e', '5f6fcd913e024366a9cee53f06e285ed8bd197d399e2d5ae5c8c73211cb4db75'), 'scripts/source/JString.psc': ('1a3d2c9c4160a3b18697e4ed083240f1f4e2ec7f889c6eada02193b296cefd06', '1a3d2c9c4160a3b18697e4ed083240f1f4e2ec7f889c6eada02193b296cefd06'), 'scripts/source/JValue.psc': ('ae221a54ea3833070266499cb708b862d6a74ec496c539a41558ef534ec0b446', '7b076b4fbed09a8e9af65e6efd0e6831fed1af4353eaee9199d58cdb081c8d29'), 'SKSE/Plugins/JContainers64.dll': ('3fcd32150c68f1691fe225a76f44911d35cfd0211257190484d1be790de23dac', '7fe27fccabf99d1e645ee79a1348eb54f0d72097179eb75511afd930ba3b6976'), 'SKSE/Plugins/JCData/Domains/.force-install': ('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'), 'SKSE/Plugins/JCData/InternalLuaScripts/api_for_lua.h': ('ab6e4fe8eec4df1dec8995a73517c2d653ddb820921da52b6e4b2543d764c198', 'ab6e4fe8eec4df1dec8995a73517c2d653ddb820921da52b6e4b2543d764c198'), 'SKSE/Plugins/JCData/InternalLuaScripts/init.lua': ('04cb58ba4a9093774acb1318e93547014ce20978d9bc952a2626ce43a8b24252', '04cb58ba4a9093774acb1318e93547014ce20978d9bc952a2626ce43a8b24252'), 'SKSE/Plugins/JCData/InternalLuaScripts/jc.lua': ('cf4e0477f2b9779f65616611bc5ea7cb7711c21f2a230d3684548eda7db3469a', 'cf4e0477f2b9779f65616611bc5ea7cb7711c21f2a230d3684548eda7db3469a'), 'SKSE/Plugins/JCData/lua/jc/init.lua': ('4abf52a89a14a043c5818cdd0548eb5e7053737020cfdf738b4e39ce383d3986', '4abf52a89a14a043c5818cdd0548eb5e7053737020cfdf738b4e39ce383d3986'), 'SKSE/Plugins/JCData/lua/testing/basic.lua': ('4a87770e89bc6f9605762d34fd57f7f7bb8c34d579723045f320744135daa54c', '4a87770e89bc6f9605762d34fd57f7f7bb8c34d579723045f320744135daa54c'), 'SKSE/Plugins/JCData/lua/testing/init.lua': ('51ae0a8469e36a283df9a70ce68cdbcc3c052c1604471a4d9c640678dfe21849', '51ae0a8469e36a283df9a70ce68cdbcc3c052c1604471a4d9c640678dfe21849'), 'SKSE/Plugins/JCData/lua/testing/jc-tests.lua': ('cbfba03c2d1f0e508018d076b8092ec457092f200815bb3f202fa10ad6755912', 'cbfba03c2d1f0e508018d076b8092ec457092f200815bb3f202fa10ad6755912'), 'SKSE/Plugins/JCData/lua/testing/misc.lua': ('ded27db6fcfec3c85db3432f2c47e34e73f1dd57dbf4876c85e4f381bb22f75c', 'ded27db6fcfec3c85db3432f2c47e34e73f1dd57dbf4876c85e4f381bb22f75c'), 'SKSE/Plugins/JCData/lua/testing/test.lua': ('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def safe(path):
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('Linked path: ' + str(path))
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError('Hard-linked file: ' + str(path))

def install(lab, staged=None, restore=False):
    lab = Path(lab).absolute()
    safe(lab)
    marker = json.loads((lab / 'LORERIM_LAB.json').read_text(encoding='utf-8-sig'))
    source = Path(marker['source']).resolve()
    resolved = lab.resolve()
    if resolved == source or resolved in source.parents or source in resolved.parents:
        raise ValueError('Original/overlapping installation refused')
    if os.name != 'nt':
        raise OSError('Windows required')
    processes = subprocess.check_output(['tasklist', '/fo', 'csv', '/nh'], text=True).lower()
    if any('"'+n+'"' in processes for n in ('skyrimse.exe','skyrimtogether.exe')):
        raise ValueError('Close game clients first')
    target = lab / 'mods/JContainers SE'
    backup = lab / 'jcontainers-update-backup'
    changes = [(rel, old, new) for rel,(old,new) in FILES.items() if old != new]
    for rel, old, new in changes:
        t, b = target / rel, backup / rel
        safe(t); safe(b)
        if sha(t) not in (old,new):
            raise ValueError('Unexpected installed file: '+rel)
        if b.exists() and sha(b) != old:
            raise ValueError('Unexpected backup: '+rel)
        if old is not None and sha(t) == new and sha(b) != old:
            raise ValueError('Missing verified original backup: '+rel)
        if restore and old is not None and sha(t) != old and sha(b) != old:
            raise ValueError('Missing original: '+rel)
    with tempfile.TemporaryDirectory(prefix='jc-release-') as temporary:
        if not restore:
            if staged is None:
                archive = Path(temporary)/'release.7z'
                urllib.request.urlretrieve(URL,archive)
                if sha(archive) != ARCHIVE_SHA256:
                    raise ValueError('Archive digest mismatch')
                subprocess.run(['tar','-xf',str(archive),'-C',temporary],check=True)
                staged = Path(temporary)/'Data'
            staged = Path(staged)
            for rel, (_, new) in FILES.items():
                if sha(staged/rel) != new:
                    raise ValueError('Release file digest mismatch: '+rel)
        for rel, old, new in changes:
            t,b = target/rel, backup/rel
            if not restore and old is not None and not b.exists():
                b.parent.mkdir(parents=True,exist_ok=True)
                with b.open('xb') as out:
                    out.write(t.read_bytes())
                if sha(b) != old:
                    raise ValueError('Backup failed: '+rel)
        for rel, old, new in changes:
            t,b = target/rel, backup/rel
            wanted = old if restore else new
            if sha(t) == wanted:
                continue
            if wanted is None:
                t.unlink()
            else:
                data = b.read_bytes() if restore else (staged/rel).read_bytes()
                t.parent.mkdir(parents=True,exist_ok=True)
                fd,name = tempfile.mkstemp(dir=t.parent,suffix='.jc-update-tmp')
                try:
                    with os.fdopen(fd,'wb') as out:
                        out.write(data); out.flush(); os.fsync(out.fileno())
                    os.replace(name,t)
                finally:
                    if Path(name).exists(): Path(name).unlink()
            if sha(t) != wanted:
                raise ValueError('Installed file verification failed: '+rel)
    return {'status':'restored' if restore else 'installed','release':'4.2.13.1',
            'changed_files':len(changes),'dll_sha256':sha(target/'SKSE/Plugins/JContainers64.dll')}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('lab');p.add_argument('--staged-data');p.add_argument('--restore',action='store_true')
    args=p.parse_args()
    print(json.dumps(install(args.lab,args.staged_data,args.restore),indent=2))
