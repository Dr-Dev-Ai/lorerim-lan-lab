"""Read-only disassembly of server health-broadcast error call sites."""
import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'analysis-libs'))
import pefile, capstone

p = Path('L:/server/STServer.dll')
raw = p.read_bytes()
print('FILE', p, 'SHA256', hashlib.sha256(raw).hexdigest())
pe = pefile.PE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
mapped = pe.get_memory_mapped_image()
needle = b'ActorValueService::OnHealthChangeBroadcast'
hits, start = [], 0
while True:
    off = raw.find(needle, start)
    if off < 0: break
    hits.append(base + pe.get_rva_from_offset(off))
    start = off + len(needle)
print('STRING VAS', [hex(x) for x in hits])
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
md.skipdata = True
funcs = []
for sec in pe.sections:
    if not sec.Characteristics & 0x20000000: continue
    for ins in md.disasm(sec.get_data(), base + sec.VirtualAddress):
        if ins.id == 0:
            continue
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                target = ins.address + ins.size + op.mem.disp
                if target in hits:
                    rva = ins.address - base
                    fn = next((e.struct for e in pe.DIRECTORY_ENTRY_EXCEPTION
                               if e.struct.BeginAddress <= rva < e.struct.EndAddress), None)
                    if fn and fn.BeginAddress not in funcs:
                        funcs.append(fn.BeginAddress)
                        print('FUNCTION', hex(fn.BeginAddress), hex(fn.EndAddress))
                        for line in md.disasm(mapped[fn.BeginAddress:fn.EndAddress],
                                             base+fn.BeginAddress):
                            print(hex(line.address), line.bytes.hex(), line.mnemonic, line.op_str)
