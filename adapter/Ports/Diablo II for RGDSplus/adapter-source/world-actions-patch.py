"""Reproducible, hash-gated instruction edits to the recovered action adapter.

This is not a rebuild of the missing world_probe.c. The fixed 1.13d core is
untouched; the original adapter remains in runtime/ for byte-level auditing.
"""
import hashlib
import json
from pathlib import Path
import struct

BASE_SHA256='d2e354af9f17dcc9bbb999918a47dbaa030885c13c5b986d8a1716f312c90e9e'
STAMINA_STUB=(0xe3520003,0x112fff18,0xe92d401f,0xe1a00003,0xe3a0100a,
              0xe3a02000,0xe301c1a4,0xe340c007,0xe088c00c,0xe12fff3c,
              0xe3500000,0xe8bd401f,0xd3a02001,0xe12fff18)


def patch(data):
    if hashlib.sha256(data).hexdigest()!=BASE_SHA256:
        raise ValueError('Unrecognized recovered world_probe.so; refusing instruction edits')
    result=bytearray(data)
    edits=[{
        'offset':0x36cc,'before':0xe3580005,'after':0xe3580006,
        'purpose':'combat_pick loop includes UNIT_TILE (5) for native warp/entrance interaction',
    },{
        'offset':0x3fc0,'before':0xe12fff38,'after':0xeb001212,
        'purpose':'route WALK_PATH through the native stamina eligibility check',
    }]
    for edit in edits:
        if struct.unpack_from('<I',data,edit['offset'])[0]!=edit['before']:
            raise ValueError('Action instruction identity mismatch')
        struct.pack_into('<I',result,edit['offset'],edit['after'])
    # The original RX segment ends at 0x8808. Its zero-filled alignment gap
    # reaches 0x8f08, before the next file-backed segment. Extend only RX's
    # declared size to cover a 56-byte position-independent ARM thunk.
    if struct.unpack_from('<8I',data,52)!=(1,0,0,0,0x8808,0x8808,5,0x1000) or any(data[0x8808:0x8f08]):
        raise ValueError('Unrecognized ELF segment or occupied instruction padding')
    stub=struct.pack('<'+'I'*len(STAMINA_STUB),*STAMINA_STUB)
    result[0x8810:0x8810+len(stub)]=stub
    struct.pack_into('<II',result,52+16,0x8850,0x8850)
    result=bytes(result)
    return result,{'schema':1,'origin':'minimal instruction patches, not recovered source',
                   'baseSha256':BASE_SHA256,'sha256':hashlib.sha256(result).hexdigest(),
                   'edits':edits,'coreModified':False,
                   'staminaThunk':{'offset':0x8810,'bytes':len(stub),
                       'sha256':hashlib.sha256(stub).hexdigest(),
                       'assembly':'world-actions.S','statId':10,'runRequires':'stamina > 0',
                       'rxSegmentSizeBefore':0x8808,'rxSegmentSizeAfter':0x8850}}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    data,receipt=patch(args.source.read_bytes())
    if args.output.exists():raise FileExistsError(args.output)
    args.output.write_bytes(data)
    args.output.with_suffix('.patch.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))
