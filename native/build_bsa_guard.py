"""Build the adapter against local installed metadata; distributes no mod DLL."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

NATIVE_HASH = '05e073b2083c2fb491902e95bbc16a06eaf75187354e552100decdc9e74fc640'


def build(compiler, native, output, minhook):
    import pefile  # Build-time dependency only; runtime adapter uses Windows APIs.
    data = native.read_bytes()
    if hashlib.sha256(data).hexdigest() != NATIVE_HASH:
        raise ValueError('Only the inspected BSAMemoryMap 1.6.0 DLL is supported')
    pe = pefile.PE(data=data)
    exports = {entry.name: entry.address for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    metadata = pe.get_data(exports[b'SKSEPlugin_Version'], 848)
    if len(metadata) != 848:
        raise ValueError('Missing version metadata')
    source = Path(__file__).with_name('bsa_map_guard.c')
    minhook_commit = subprocess.check_output(['git', '-C', str(minhook), 'rev-parse', 'HEAD'], text=True).strip()
    if minhook_commit != 'c3fcafdc10146beb5919319d0683e44e3c30d537':
        raise ValueError('Build requires the inspected MinHook v1.3.4 commit')
    if subprocess.check_output(['git', '-C', str(minhook), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise ValueError('MinHook tracked sources must be unchanged')
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bsa-build-') as folder:
        include = Path(folder) / 'bsa_guard_build.h'
        byte_list = lambda values: '{' + ','.join(str(value) for value in values) + '}'
        include.write_text('#define BSA_NATIVE_HASH ' + byte_list(bytes.fromhex(NATIVE_HASH)) +
                           '\n#define BSA_VERSION_DATA ' + byte_list(metadata) + '\n')
        command = [str(compiler.resolve()), 'cc', '-target', 'x86_64-windows-gnu',
                   '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-shared',
                   '-I', folder, '-I', str((minhook / 'include').resolve()),
                   '-Wno-cast-function-type-mismatch', str(source.resolve()),
                   *[str((minhook / path).resolve()) for path in
                     ('src/buffer.c', 'src/hook.c', 'src/trampoline.c', 'src/hde/hde64.c')],
                   '-o', str(output), '-lbcrypt', '-luser32']
        subprocess.run(command, check=True)
    report = {'native_sha256': NATIVE_HASH, 'adapter_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'compiler_version': subprocess.check_output([str(compiler.resolve()), 'version'], text=True).strip(),
              'version_metadata_sha256': hashlib.sha256(metadata).hexdigest(), 'command': command}
    report['minhook_commit'] = minhook_commit
    output.with_suffix('.build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--minhook', type=Path, required=True)
    args = parser.parse_args()
    build(args.compiler, args.native, args.output, args.minhook)
