import argparse
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct


import frontend_decode as assets
from types import SimpleNamespace


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def repair(retail,patch,output):
    args = SimpleNamespace(retail=Path(retail),patch=Path(patch),output=Path(output))
    output = args.output.resolve()
    if output.exists() or output==args.patch.resolve() or output.is_relative_to(args.retail.resolve()):
        raise ValueError('Output must be a new file outside the source installation')
    source = args.retail/'d2exp.mpq'
    archive = ctypes.c_void_p()
    library = assets.storm.lib
    if not library.SFileOpenArchive(str(source),0,0x100,ctypes.byref(archive)):
        raise OSError('Cannot open retail expansion archive')
    original = 'data\\global\\ui\\PANEL\\invchar6.dc6'
    target = 'data\\local\\ui\\InvChar6.dc6'
    try:
        data = assets.read(archive,original)
    finally:
        library.SFileCloseArchive(archive)
    frames = assets.frames(data)
    if [frame[:2] for frame in frames]!=[(256,256),(64,256),(256,176),(64,176)]*2:
        raise ValueError('Unexpected retail inventory panel dimensions')
    parent_hash = digest(args.patch)
    output.parent.mkdir(parents=True,exist_ok=True)
    with assets.mpq.Archive(assets.storm,args.patch) as parent:
        identity = tuple(assets.mpq.name_hash(target,kind) for kind in (1,2))+(0,)
        _,block = parent.identities[identity]
        blocks = list(parent.blocks)
        with args.patch.open('rb') as source_stream,output.open('xb') as output_stream:
            shutil.copyfileobj(source_stream,output_stream)
            blocks[block] = (output_stream.tell(),len(data),len(data),0x80000000)
            output_stream.write(data)
            hash_offset = output_stream.tell()
            output_stream.write(assets.mpq.encrypt_table(b''.join(struct.pack('<4I',*entry) for entry in parent.hashes),'(hash table)'))
            block_offset = output_stream.tell()
            output_stream.write(assets.mpq.encrypt_table(b''.join(struct.pack('<4I',*entry) for entry in blocks),'(block table)'))
            total = output_stream.tell()
            header = list(struct.unpack('<4sIIHHIIII',parent.header))
            header[2],header[5],header[6] = total,hash_offset,block_offset
            output_stream.seek(0)
            output_stream.write(struct.pack('<4sIIHHIIII',*header))
    if not library.SFileOpenArchive(str(output),0,0x100,ctypes.byref(archive)):
        raise OSError('Cannot reopen experiment patch')
    try:
        if assets.read(archive,target)!=data:
            raise ValueError('Replacement readback differs')
    finally:
        library.SFileCloseArchive(archive)
    with assets.mpq.Archive(assets.storm,args.patch) as parent,assets.mpq.Archive(assets.storm,output) as updated:
        if parent.hashes!=updated.hashes:
            raise ValueError('Unrelated lookup table changed')
        for index,record in enumerate(parent.blocks):
            if index!=block and (record!=updated.blocks[index] or parent.raw(index)!=updated.raw(index)):
                raise ValueError('Unrelated archive block changed')
    report = {'schema':1,'purpose':'private-frontend-lab-retail-inventory',
              'parentPatchSha256':parent_hash,'retailArchive':str(source.resolve()),
              'retailArchiveSha256':digest(source),'sourceResource':original,'targetResource':target,
              'resourceSha256':hashlib.sha256(data).hexdigest(),'size':output.stat().st_size,
              'sha256':digest(output),'coreChanged':False,'inventoryTableChanged':False}
    return report
