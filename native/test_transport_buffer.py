"""Run the native buffer regression against pinned upstream TiltedCore sources."""
import argparse
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--compiler', type=Path, required=True)
p.add_argument('--core', type=Path, required=True)
p.add_argument('--plugins', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
commit = subprocess.check_output(['git', '-C', str(a.core), 'rev-parse', 'HEAD'], text=True).strip()
if commit != 'b5aa9203dc47e3ced49ca60e65d1bf4409501f03':
    raise ValueError('Requires TiltedCore v0.2.9')
if subprocess.check_output(['git', '-C', str(a.core), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
    raise ValueError('TiltedCore tracked sources must be unchanged')
a.output.parent.mkdir(parents=True, exist_ok=True)
base = a.core / 'Code/core'
subprocess.run([str(a.compiler.resolve()), 'c++', '-std=c++20', '-O2', '-I', str(base / 'include'),
                str(Path(__file__).with_name('transport_buffer_test.cpp')),
                str(base / 'src/Buffer.cpp'), str(base / 'src/ScratchAllocator.cpp'),
                '-o', str(a.output)], check=True)
subprocess.run([str(a.output.resolve()), str(a.plugins)], check=True)
