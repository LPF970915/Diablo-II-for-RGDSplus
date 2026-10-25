import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import uuid


sys.path.insert(0,str(Path(__file__).resolve().parent))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def local_path(path):
    path = Path(os.path.abspath(path))
    for ancestor in (path,*path.parents):
        if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.stat(),'st_file_attributes',0)&0x400):
            raise ValueError('Linked folders are not supported: '+str(ancestor))
    return path


def verify_runtime(payload):
    manifest = json.loads((payload/'runtime-manifest.json').read_text(encoding='utf-8'))
    if not manifest['externalCoreRequired'] or not manifest['playerFrontendCacheGeneration']:
        raise ValueError('This importer requires the matching fresh-player adapter')
    for name,record in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in name or '\\' in name:
            raise ValueError('Unsafe runtime path')
        path = local_path(payload/name)
        if path.stat().st_size!=record['size'] or digest(path)!=record['sha256']:
            raise ValueError('Damaged adapter file: '+name)
    return manifest


def install(payload,source):
    payload,source = local_path(payload),local_path(source)
    if not source.is_dir() or source==payload or source.is_relative_to(payload) or payload.is_relative_to(source):
        raise ValueError('Use a separate original game folder and a fresh extracted adapter folder')
    for name in ('gamedata','private-assets','prefix.ext4','libd2game_sa_arm.exe.so','installation-report.json'):
        path = local_path(payload/name)
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError('Not a fresh adapter folder: '+name+'. Nothing was replaced.')
    saves = local_path(payload/'saves')
    if saves.exists() and any(saves.iterdir()):
        raise ValueError('Existing saves detected. Use a new extracted folder.')
    print('1/3 Checking adapter, downloaded core and embedded Chinese patch...',flush=True)
    runtime = verify_runtime(payload)
    bundle = payload/'game-import/chinese-patch'
    for name,record in runtime['supplementFiles'].items():
        path = local_path(bundle/name)
        if not path.is_file() or path.stat().st_size!=record['size'] or digest(path)!=record['sha256']:
            raise ValueError('Re-extract the adapter ZIP; embedded Chinese patch is missing: '+name)
    engine = 'libd2game_sa_arm.exe.so'
    supplied = [payload/'engine-input'/name for name in (engine,engine+'.xz') if (payload/'engine-input'/name).is_file()]
    if len(supplied)!=1:
        raise ValueError('Put exactly one author-provided .so.xz or .so into engine-input; see the download guide.')
    from prepare_external_core import prepare
    prepare(payload,check_only=True)
    stage = payload/('.fresh-import-'+uuid.uuid4().hex)
    stage.mkdir()
    log_directory = payload/'logs'
    log_directory.mkdir(exist_ok=True)
    log_path = log_directory/('import-'+str(time.time_ns())+'.log')
    moved = []
    try:
        shutil.copy2(payload/'runtime-manifest.json',stage/'runtime-manifest.json')
        (stage/'engine-input').mkdir()
        shutil.copy2(supplied[0],stage/'engine-input'/supplied[0].name)
        (stage/'game-import/engine').mkdir(parents=True)
        for name in ('recipe.json','classic.bsdiff'):
            shutil.copy2(payload/'game-import/engine'/name,stage/'game-import/engine'/name)
        powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        command = [str(powershell),'-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',
                   str(payload/'game-import/Import Game Assets.ps1'),'-SourceDirectory',str(source),
                   '-GameDirectory',str(stage),'-SkipRuntimeCheck']
        print('2/3 Importing your licensed resources and rebuilding Chinese patch. Please wait...',flush=True)
        print('Detailed import log: '+str(log_path),flush=True)
        with log_path.open('xb') as stream:
            result = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:
            print(log_path.read_text(encoding='utf-8',errors='replace')[-8000:],flush=True)
            raise RuntimeError('Original resource validation/import failed. Read the log above.')
        from prepare_inventory import repair
        original = stage/'chinese-before-retail.mpq'
        (stage/'gamedata/Patch_D2.mpq').rename(original)
        patch = repair(source,original,stage/'gamedata/Patch_D2.mpq')
        if patch['sha256']!=runtime['retailInventoryPatchSha256']:
            raise ValueError('Retail inventory patch differs from tested device version')
        resources = json.loads((stage/'gamedata/resource-manifest.json').read_text(encoding='utf-8-sig'))
        for record in resources['files']:
            if record['name']=='Patch_D2.mpq':
                record.update(size=patch['size'],sha256=patch['sha256'],origin='chinese-supplement-plus-user-retail-inventory')
        resources['copiedBytes'] = sum(record['size'] for record in resources['files'])
        (stage/'gamedata/resource-manifest.json').write_text(json.dumps(resources,indent=2)+'\n',encoding='utf-8')
        print('3/3 Generating dual-screen backgrounds, animated logo and subtitles from your MPQs...',flush=True)
        from prepare_frontend import generate
        frontend = generate(stage/'gamedata',stage/'private-assets')
        for name in ('gamedata','private-assets',engine):
            target = local_path(payload/name)
            if target.exists():
                target.rmdir()
            (stage/name).rename(target)
            moved.append(name)
        report = {'schema':1,'build':runtime['build'],'source':str(source),'originalSourceModified':False,
                  'coreSha256':digest(payload/engine),'retailInventoryPatch':patch,
                  'frontendFiles':frontend['files'],'prefixImported':False,'savesImported':False,
                  'freshDeviceInstallationTested':False,'importLog':str(log_path)}
        with (payload/'installation-report.json').open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2)
    except BaseException:
        for name in reversed(moved):
            (payload/name).rename(stage/name)
        print('Incomplete import kept at: '+str(stage),flush=True)
        raise
    if stage.resolve().parent!=payload.resolve() or not stage.name.startswith('.fresh-import-'):
        raise ValueError('Refusing cleanup outside the importer-owned staging folder')
    shutil.rmtree(stage)
    print('INSTALLATION READY: '+str(payload),flush=True)
    print('No player saves or existing initialized prefix were imported. Original PC files were not modified.',flush=True)
    print('Copy the prepared Ports folder to the card only after backing up its existing same-name installation.',flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',default=os.environ.get('D2_IMPORT_SOURCE',''))
    parser.add_argument('--payload',type=Path,default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    if not args.source:
        raise ValueError('Run Import Game Assets.cmd and enter your original Diablo II + LoD folder')
    install(args.payload,Path(args.source.strip().strip('"')))


if __name__=='__main__':
    try:
        main()
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print('IMPORT FAILED: '+str(error),file=sys.stderr,flush=True)
        sys.exit(1)
