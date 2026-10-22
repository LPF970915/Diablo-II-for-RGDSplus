"""Prepare a player-supplied notaz core without downloading game code."""
import argparse
import bz2
import hashlib
import json
import lzma
from pathlib import Path
import sys

ENGINE = 'libd2game_sa_arm.exe.so'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signed_offset(data):
    value = int.from_bytes(data, 'little')
    return -(value & ((1 << 63) - 1)) if value >> 63 else value


def apply_delta(original, patch, size):
    if len(patch) < 32 or patch[:8] != b'BSDIFF40':
        raise ValueError('Invalid adapter delta')
    control_size, diff_size, output_size = [signed_offset(patch[index:index+8]) for index in (8, 16, 24)]
    if output_size != size or min(control_size, diff_size) < 0 or 32 + control_size + diff_size > len(patch):
        raise ValueError('Invalid adapter delta sizes')
    control = bz2.decompress(patch[32:32+control_size])
    differences = bz2.decompress(patch[32+control_size:32+control_size+diff_size])
    extra = bz2.decompress(patch[32+control_size+diff_size:])
    if len(control) % 24 or len(differences) > size or len(extra) > size:
        raise ValueError('Invalid adapter delta streams')
    output = bytearray(size)
    old_position = new_position = diff_position = extra_position = 0
    for cursor in range(0, len(control), 24):
        copy_size, extra_size, adjustment = [signed_offset(control[cursor+offset:cursor+offset+8]) for offset in (0, 8, 16)]
        if min(copy_size, extra_size) < 0 or new_position + copy_size + extra_size > size:
            raise ValueError('Invalid adapter delta output range')
        if diff_position + copy_size > len(differences) or extra_position + extra_size > len(extra):
            raise ValueError('Truncated adapter delta')
        output[new_position:new_position+copy_size] = differences[diff_position:diff_position+copy_size]
        for index in range(copy_size):
            if 0 <= old_position + index < len(original):
                output[new_position+index] = (output[new_position+index] + original[old_position+index]) & 255
        new_position += copy_size
        old_position += copy_size + adjustment
        diff_position += copy_size
        output[new_position:new_position+extra_size] = extra[extra_position:extra_position+extra_size]
        new_position += extra_size
        extra_position += extra_size
    if new_position != size or diff_position != len(differences) or extra_position != len(extra):
        raise ValueError('Incomplete adapter delta')
    return bytes(output)


def validate_output(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked output is not supported: ' + str(ancestor))
    return path


def prepare(payload, check_only=False):
    payload = validate_output(payload)
    recipe_path = payload/'game-import/engine/recipe.json'
    recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
    output = validate_output(payload/ENGINE)
    if output.exists():
        if digest(output.read_bytes()) != recipe['outputSha256']:
            raise ValueError('Existing core differs. Use a fresh adapter folder; nothing was overwritten.')
        return recipe['outputSha256']
    candidates = [payload/'engine-input'/name for name in (ENGINE, ENGINE+'.xz')]
    supplied = [path for path in candidates if path.is_file()]
    if len(supplied) != 1:
        raise ValueError('Place exactly one official '+ENGINE+' or '+ENGINE+'.xz in engine-input. See README.zh-CN.txt; PND r4 and 1.14 cores are not supported.')
    source = supplied[0]
    compressed = source.name.endswith('.xz')
    data = source.read_bytes()
    expected_size = recipe['archiveSize'] if compressed else recipe['inputSize']
    expected_hash = recipe['archiveSha256'] if compressed else recipe['inputSha256']
    if len(data) != expected_size or digest(data) != expected_hash:
        raise ValueError('Unsupported official core version. Download the pinned standalone .xz from the author; do not use the current Pandora PND r4.')
    if compressed:
        data = lzma.decompress(data)
    if len(data) != recipe['inputSize'] or digest(data) != recipe['inputSha256']:
        raise ValueError('Official core checksum mismatch')
    delta = recipe_path.with_name('classic.bsdiff').read_bytes()
    if digest(delta) != recipe['deltaSha256']:
        raise ValueError('Adapter delta checksum mismatch')
    prepared = apply_delta(data, delta, recipe['outputSize'])
    if digest(prepared) != recipe['outputSha256']:
        raise ValueError('Prepared core does not match the classic device baseline')
    if not check_only:
        temporary = validate_output(output.with_suffix('.so.importing'))
        with temporary.open('xb') as stream:
            stream.write(prepared)
        try:
            if output.exists():
                raise FileExistsError(output)
            temporary.rename(output)
        except FileExistsError:
            raise ValueError('Core output appeared during preparation; nothing was replaced')
    return recipe['outputSha256']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    arguments = parser.parse_args()
    try:
        print('Classic ARM core verified:', prepare(arguments.payload, arguments.check_only))
    except (OSError, ValueError, KeyError, lzma.LZMAError) as error:
        sys.exit('Core preparation failed: ' + str(error))
