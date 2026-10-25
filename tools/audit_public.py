"""Audit the curated public snapshot and the immutable accepted release archive."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(archive=None):
    expected = json.loads((ROOT/'packaging/source-manifest.json').read_text(encoding='utf-8'))
    baseline = json.loads((ROOT/'packaging/accepted-baseline.json').read_text(encoding='utf-8'))
    actual = {p.relative_to(ROOT).as_posix():p for p in (ROOT/'adapter').rglob('*') if p.is_file()}
    if set(actual) != set(expected):
        raise ValueError('Source allowlist mismatch')
    for name, path in actual.items():
        data = path.read_bytes()
        if {'size':len(data),'sha256':digest(data)} != expected[name]:
            raise ValueError('Source bytes differ: '+name)
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if '.git' in relative.parts or not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Symlink in public snapshot')
        if any(p.lower() in {'tests','diagnostics','logs','recovery','private-assets','chinese-patch','gamedata','saves'} for p in relative.parts):
            raise ValueError('Private directory: '+str(relative))
        if path.suffix.lower() in {'.mpq','.d2s','.key','.ma0','.map','.log','.pyc','.so','.dll','.runtime','.zip','.ext4'}:
            raise ValueError('Unexpected binary/private file: '+str(relative))
        data = path.read_bytes()
        if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)',data):
            raise ValueError('Possible credential: '+str(relative))
    if archive:
        manifest = json.loads((ROOT/'packaging'/baseline['packageManifest']).read_text(encoding='utf-8'))
        path = Path(archive)
        if baseline.get('adapter',{}).get('sha256') != manifest.get('sha256'):
            raise ValueError('Accepted baseline and package manifest disagree')
        if digest(path.read_bytes()) != manifest['sha256']:
            raise ValueError('Not the accepted release ZIP')
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise ValueError('ZIP CRC failure')
            members = [i for i in z.infolist() if not i.is_dir()]
            if len({i.filename for i in members}) != len(members):
                raise ValueError('Duplicate ZIP member')
            if {i.filename for i in members} != set(manifest['files']):
                raise ValueError('ZIP allowlist mismatch')
            for member in members:
                name = PurePosixPath(member.filename)
                if name.is_absolute() or '..' in name.parts or ':' in str(name) or '\\' in str(name):
                    raise ValueError('Unsafe ZIP member')
                if ((name.suffix.lower() in {'.mpq','.d2s','.key','.ma0','.map','.log','.pyc'} and 'game-import/chinese-patch' not in name.as_posix()) or name.name in {'prefix.ext4','libd2game_sa_arm.exe.so'}):
                    raise ValueError('Private/game file in ZIP')
                data = z.read(member)
                if {'size':len(data),'sha256':digest(data)} != manifest['files'][member.filename]:
                    raise ValueError('ZIP member mismatch')
    print('PASS: curated source allowlist and credential checks'+(
        f"; {len(manifest['files'])} {manifest['build']} ZIP files verified" if archive else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive')
    audit(parser.parse_args().archive)
