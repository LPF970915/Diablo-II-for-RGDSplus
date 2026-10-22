"""Read-only preflight for packaged offline dependencies and the prepared engine."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def sha(file):
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            digest.update(data)
    return digest.hexdigest()


def verify(payload):
    payload = Path(payload)
    manifest = json.loads((payload/'runtime-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('runtimeNetworkRequired') is not False:
        raise ValueError('Unsupported runtime manifest')
    for name, record in manifest['files'].items():
        parts = PurePosixPath(name).parts
        if '..' in parts or name.startswith(('/', '\\')) or '\\' in name:
            raise ValueError('Unsafe runtime manifest path')
        file = payload/name
        if file.stat().st_size != record['size'] or sha(file) != record['sha256']:
            raise ValueError('Runtime checksum mismatch: ' + name)
    engine = payload/'libd2game_sa_arm.exe.so'
    if not engine.is_file() or sha(engine) != manifest['engineSha256']:
        raise ValueError('Prepared ARM engine missing or invalid; run Import resources.cmd on the PC first')
    return len(manifest['files'])


if __name__ == '__main__':
    try:
        print('Offline runtime and ARM engine verified:', verify(sys.argv[1]), 'support files')
    except (OSError, ValueError, KeyError) as error:
        sys.exit('Preflight failed: '+str(error))
