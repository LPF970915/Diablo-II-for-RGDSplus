"""Clear PF_X from PT_GNU_STACK so glibc does not ask for an executable stack."""
import struct, sys
path = sys.argv[1]
PT_GNU_STACK = 0x6474E551
PF_X = 1
f = open(path, 'r+b')
try:
    ident = f.read(16)
    if ident[:4] != b'\x7fELF':
        sys.exit('not an ELF file')
    fields = f.read(36)
    if len(fields) != 36:
        sys.exit('truncated header')
    e_phoff, = struct.unpack_from('<I', fields, 12)
    e_phentsize, e_phnum = struct.unpack_from('<HH', fields, 26)
    found = 0
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        f.seek(off)
        phdr = f.read(32)
        p_type, = struct.unpack_from('<I', phdr, 0)
        if p_type != PT_GNU_STACK:
            continue
        p_flags, = struct.unpack_from('<I', phdr, 24)
        found += 1
        if p_flags & PF_X:
            f.seek(off + 24)
            f.write(struct.pack('<I', p_flags & ~PF_X))
            print(f'patched PT_GNU_STACK flags {p_flags:#x} -> {p_flags & ~PF_X:#x}')
        else:
            print(f'PT_GNU_STACK already non-executable ({p_flags:#x})')
    print('PT_GNU_STACK entries seen:', found)
finally:
    f.close()
