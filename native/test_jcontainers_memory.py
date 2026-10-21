import ctypes,sys,json
from pathlib import Path
p=Path(sys.argv[1]).resolve()
import hashlib
if hashlib.sha256(p.read_bytes()).hexdigest() not in ('3fcd32150c68f1691fe225a76f44911d35cfd0211257190484d1be790de23dac','7fe27fccabf99d1e645ee79a1348eb54f0d72097179eb75511afd930ba3b6976'):
 raise ValueError('Unsupported DLL for native regression')
dll=ctypes.CDLL(str(p))
dll.JC_versionString.restype=ctypes.c_char_p
print('version:',dll.JC_versionString().decode(),flush=True)
held=[]
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.VirtualAlloc.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint32];k.VirtualAlloc.restype=ctypes.c_void_p
k.VirtualFree.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]
if '--reserve-low' in sys.argv:
 for addr in range(0x10000,0x80000000,0x10000):
  ptr=k.VirtualAlloc(addr,0x10000,0x2000,1)
  if ptr: held.append(ptr)
 print('Reserved free address space below 2 GiB:',len(held)*65536,'bytes; RAM not committed.',flush=True)
a=[b'jc-tests',b'--gtest_filter=fixture.Lua_evalLua:fixture.Lua_launch_all_lua_tests']
av=(ctypes.c_char_p*len(a))(*a)
try:
 result=int(dll.JC_runTests(len(a),av));print('test status:',result,flush=True)
except OSError as e:
 print('Native test exception:',e,flush=True);result=2
finally:
 for addr in held:k.VirtualFree(addr,0,0x8000)
sys.exit(result)
