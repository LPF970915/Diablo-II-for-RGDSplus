"""Verify the imported retail resources used by the classic controller baseline."""
import argparse
import hashlib
import json
from pathlib import Path


REQUIRED = {
    'd2char.mpq', 'd2data.mpq', 'd2exp.mpq', 'd2music.mpq', 'd2sfx.mpq',
    'd2speech.mpq', 'd2video.mpq', 'd2xmusic.mpq', 'd2xtalk.mpq',
    'd2xvideo.mpq', 'Patch_D2.mpq', 'D2.LNG',
}


def verify(folder, full=False):
    folder = Path(folder)
    manifest = json.loads((folder / 'resource-manifest.json').read_text(encoding='utf-8-sig'))
    profile = str(manifest.get('profile', ''))
    if not profile.startswith('retail-enUS-1.14b'):
        raise ValueError('unsupported resource profile: ' + profile)
    files = manifest.get('files', [])
    names = {entry.get('name') for entry in files}
    if manifest.get('schema') not in (2, 3) or not REQUIRED.issubset(names):
        raise ValueError('unsupported or incomplete retail resource manifest')
    if manifest.get('schema') == 3:
        names.add('frontend-environment.bgra')
    actual = {file.name for file in folder.iterdir() if file.name != 'BnetLog.txt'}
    if actual != names | {'resource-manifest.json'}:
        raise ValueError('unexpected files in imported gamedata')
    for entry in files:
        file = folder / entry['name']
        if file.stat().st_size != entry['size']:
            raise ValueError('resource size mismatch: ' + file.name)
        if full:
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            if digest != entry['sha256']:
                raise ValueError('resource hash mismatch: ' + file.name)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    try:
        print('Imported retail resources verified:', verify(args.folder, args.full))
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit('Resource check failed: ' + str(error))
