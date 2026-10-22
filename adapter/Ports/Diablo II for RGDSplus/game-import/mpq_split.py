"""Split a legacy Chinese MPQ by retail content identity; rebuild it locally.

Windows x64, Python 3.10+, and the project's MIT-licensed StormLib DLL.
This classifies bytes and paths; it does not certify copyright permissions.
Only standalone v1 MPQs with a metadata prefix and zero padding are supported.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DLL = ROOT / "tools/resource-migration/stormlib/x64/StormLib.dll"
RETAIL = "retail-identical"
CHANGED = "existing-path-changed"
UNMATCHED = "unmatched-candidate"
OUTPUTS = {CHANGED: "zh-CN-existing-path-changes.mpq",
           UNMATCHED: "zh-CN-unmatched-candidates.mpq"}
EXISTS = 0x80000000
UNSAFE_TO_RELOCATE = 0x00010000 | 0x00020000 | 0x00100000 | 0x02000000
MASK = 0xFFFFFFFF


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def destination(path, protected=()):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (ancestor.exists() and
                getattr(ancestor.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Output must not pass through a link: " + str(ancestor))
    path = path.resolve()
    if path.exists():
        raise FileExistsError("Refusing to replace existing output: " + str(path))
    for item in protected:
        item = Path(item).resolve()
        if path == item or path.is_relative_to(item) or item.is_relative_to(path):
            raise ValueError("Output overlaps a source or bundle: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def crypt_table():
    values = [0] * 0x500
    seed = 0x100001
    for low in range(256):
        for high in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            first = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            values[low + high * 256] = first | (seed & 0xFFFF)
    return values


CRYPT = crypt_table()


def name_hash(name, kind):
    first, second = 0x7FED7FED, 0xEEEEEEEE
    for char in name.replace("/", "\\").upper().encode("ascii"):
        first = (CRYPT[kind * 256 + char] ^ (first + second)) & MASK
        second = (char + first + second + (second << 5) + 3) & MASK
    return first


def encrypt_table(plain, name):
    if len(plain) % 4:
        raise ValueError("MPQ table is not DWORD aligned")
    first, second = name_hash(name, 3), 0xEEEEEEEE
    result = bytearray()
    for (value,) in struct.iter_unpack("<I", plain):
        second = (second + CRYPT[0x400 + (first & 255)]) & MASK
        result += struct.pack("<I", value ^ ((first + second) & MASK))
        first = (((~first << 21) + 0x11111111) | (first >> 11)) & MASK
        second = (value + second + (second << 5) + 3) & MASK
    return bytes(result)


class Storm:
    def __init__(self, dll):
        if os.name != "nt" or c.sizeof(c.c_void_p) != 8:
            raise RuntimeError("Use 64-bit Python on Windows with x64 StormLib")
        self.path = Path(dll).resolve(strict=True)
        self.lib = c.WinDLL(str(self.path), use_last_error=True)
        signatures = {
            "SFileOpenArchive": ([c.c_wchar_p, c.c_uint32, c.c_uint32,
                                   c.POINTER(c.c_void_p)], c.c_bool),
            "SFileCloseArchive": ([c.c_void_p], c.c_bool),
            "SFileOpenFileEx": ([c.c_void_p, c.c_char_p, c.c_uint32,
                                 c.POINTER(c.c_void_p)], c.c_bool),
            "SFileCloseFile": ([c.c_void_p], c.c_bool),
            "SFileGetFileSize": ([c.c_void_p, c.POINTER(c.c_uint32)], c.c_uint32),
            "SFileReadFile": ([c.c_void_p, c.c_void_p, c.c_uint32,
                               c.POINTER(c.c_uint32), c.c_void_p], c.c_bool),
            "SFileGetFileInfo": ([c.c_void_p, c.c_int, c.c_void_p, c.c_uint32,
                                  c.POINTER(c.c_uint32)], c.c_bool),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result


class Archive:
    def __init__(self, storm, path):
        self.storm = storm
        self.path = Path(path).resolve(strict=True)
        self.stream = self.path.open("rb")
        self.handle = c.c_void_p()
        try:
            header = self.stream.read(32)
            (magic, size, total, version, sector, hash_offset, block_offset,
             hash_count, block_count) = struct.unpack("<4sIIHHIIII", header)
            if (magic != b"MPQ\x1a" or size != 32 or version != 0 or
                    total != self.path.stat().st_size or hash_count == 0 or
                    hash_count > 0x80000 or block_count > 0x80000):
                raise ValueError("Unsupported standalone v1 MPQ: " + str(self.path))
            if not storm.lib.SFileOpenArchive(str(self.path), 0, 0x100,
                                              c.byref(self.handle)):
                raise OSError(c.get_last_error(), str(self.path))
            self.header = header
            self.sector_shift = sector
            self.hashes = self._table(19, hash_count)
            self.blocks = self._table(23, block_count)
            self.metadata_end = max(32, hash_offset + hash_count * 16,
                                    block_offset + block_count * 16)
            self.identities = {}
            for index, entry in enumerate(self.hashes):
                if entry[3] >= len(self.blocks):
                    continue
                if not self.blocks[entry[3]][3] & EXISTS:
                    raise ValueError("Hash points to an absent block")
                if entry[:3] in self.identities:
                    raise ValueError("Duplicate hash/locale identity")
                self.identities[entry[:3]] = (index, entry[3])
            for offset, packed, unpacked, flags in self.blocks:
                if flags & EXISTS and (offset < 32 or offset + packed > total or
                                       unpacked > 512 * 1024 * 1024):
                    raise ValueError("Invalid MPQ block range")
        except BaseException:
            self.close()
            raise

    def _table(self, info_class, count):
        needed = c.c_uint32()
        buffer = c.create_string_buffer(count * 16)
        if not self.storm.lib.SFileGetFileInfo(self.handle, info_class, buffer,
                                              len(buffer), c.byref(needed)):
            raise OSError(c.get_last_error(), "MPQ table")
        if needed.value != len(buffer):
            raise ValueError("Unexpected StormLib table ABI")
        return list(struct.iter_unpack("<4I", buffer.raw))

    def raw(self, block):
        offset, packed, _, _ = self.blocks[block]
        self.stream.seek(offset)
        data = self.stream.read(packed)
        if len(data) != packed:
            raise ValueError("Truncated MPQ block")
        return data

    def read(self, block):
        handle = c.c_void_p()
        lib = self.storm.lib
        if not lib.SFileOpenFileEx(self.handle, f"File{block:08d}.xxx".encode(),
                                  0, c.byref(handle)):
            raise OSError(c.get_last_error(), f"MPQ block {block}")
        try:
            high, got = c.c_uint32(), c.c_uint32()
            size = lib.SFileGetFileSize(handle, c.byref(high))
            if high.value or size != self.blocks[block][2]:
                raise ValueError("Unexpected decoded file size")
            data = c.create_string_buffer(size)
            if not lib.SFileReadFile(handle, data, size, c.byref(got), None):
                raise OSError(c.get_last_error(), f"Read MPQ block {block}")
            if got.value != size:
                raise ValueError("Short decoded read")
            return data.raw
        finally:
            lib.SFileCloseFile(handle)

    def close(self):
        if getattr(self, "handle", None) and self.handle.value:
            self.storm.lib.SFileCloseArchive(self.handle)
            self.handle = c.c_void_p()
        if getattr(self, "stream", None):
            self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def write_overlay(source, selected, output):
    """Relocate unencrypted raw blocks, retaining original lookup slots/locales.

    No pseudo filename is used as a real MPQ name. Real hash pairs stay intact.
    Removed slots become tombstones, preserving collision probe chains.
    """
    remap, blocks = {}, []
    with Path(output).open("xb") as stream:
        stream.write(bytes(32))
        for original_index in sorted(selected):
            _, _, decoded_size, flags = source.blocks[original_index]
            if flags & UNSAFE_TO_RELOCATE:
                raise ValueError("Encrypted/offset-key/patch blocks need a named writer")
            raw = source.raw(original_index)
            remap[original_index] = len(blocks)
            blocks.append((stream.tell(), len(raw), decoded_size, flags))
            stream.write(raw)
        hashes = []
        for h1, h2, locale_platform, block in source.hashes:
            if block in remap:
                block = remap[block]
            elif block < len(source.blocks):
                block = 0xFFFFFFFE
            hashes.append((h1, h2, locale_platform, block))
        hash_offset = stream.tell()
        stream.write(encrypt_table(b"".join(struct.pack("<4I", *h) for h in hashes),
                                   "(hash table)"))
        block_offset = stream.tell()
        stream.write(encrypt_table(b"".join(struct.pack("<4I", *b) for b in blocks),
                                   "(block table)"))
        total = stream.tell()
        if total > MASK:
            raise ValueError("v1 MPQ is too large")
        stream.seek(0)
        stream.write(struct.pack("<4sIIHHIIII", b"MPQ\x1a", 32, total, 0,
                                 source.sector_shift, hash_offset, block_offset,
                                 len(hashes), len(blocks)))


def identity_for(manifest_entry):
    return tuple(manifest_entry["identity"])


def verify_overlay(storm, path, entries):
    with Archive(storm, path) as archive:
        expected = {identity_for(e): e for e in entries}
        if set(archive.identities) != set(expected):
            raise ValueError("Overlay identity coverage differs")
        for identity, entry in expected.items():
            _, index = archive.identities[identity]
            if sha(archive.raw(index)) != entry["rawSha256"]:
                raise ValueError("Overlay raw bytes differ")
            if sha(archive.read(index)) != entry["contentSha256"]:
                raise ValueError("Overlay decoded bytes differ")


def split(storm, patch_path, retail_dir, output):
    patch_path = Path(patch_path).resolve(strict=True)
    retail_dir = Path(retail_dir).resolve(strict=True)
    output = destination(output, (patch_path, retail_dir))
    source_hash = file_sha(patch_path)
    retail_paths = sorted(retail_dir.glob("*.mpq"),
                          key=lambda p: (p.name.lower() != "patch_d2.mpq", p.name.lower()))
    if not retail_paths:
        raise ValueError("No retail MPQs found")
    if len({p.name.lower() for p in retail_paths}) != len(retail_paths):
        raise ValueError("Ambiguous retail MPQ filenames")
    with ExitStack() as stack, tempfile.TemporaryDirectory(
            prefix=".d2-cn-split-", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        patch = stack.enter_context(Archive(storm, patch_path))
        active = {i for i, b in enumerate(patch.blocks) if b[3] & EXISTS}
        referenced = {i for _, i in patch.identities.values()}
        if active != referenced or len(active) != len(patch.blocks):
            raise ValueError("Unreferenced/absent source blocks need manual review")
        if len(patch.identities) != len(active):
            raise ValueError("Multiple hash aliases per block need manual review")
        # Archive layout is metadata only; padding outside active blocks must be zero.
        original = patch_path.read_bytes()
        cursor = patch.metadata_end
        for offset, packed, _, _ in sorted(patch.blocks):
            if offset < cursor or any(original[cursor:offset]):
                raise ValueError("Overlapping blocks or nonzero unknown padding")
            cursor = offset + packed
        if any(original[cursor:]):
            raise ValueError("Nonzero unknown archive tail")
        layout = original[:patch.metadata_end]
        (stage / "archive-layout.bin").write_bytes(layout)
        decoded = {i: patch.read(i) for i in active}
        raw_hashes = {i: sha(patch.raw(i)) for i in active}
        matches = {i: [] for i in active}
        choices = {}
        for path in retail_paths:
            print("Comparing " + path.name, flush=True)
            with Archive(storm, path) as retail:
                for identity, (_, index) in patch.identities.items():
                    if identity not in retail.identities:
                        continue
                    _, retail_index = retail.identities[identity]
                    equal = retail.read(retail_index) == decoded[index]
                    match = {"archive": path.name, "contentIdentical": equal}
                    matches[index].append(match)
                    if not equal or index in choices:
                        continue
                    if (retail.sector_shift == patch.sector_shift and
                            sha(retail.raw(retail_index)) == raw_hashes[index]):
                        mode = "raw-copy"
                    elif patch.blocks[index][3] == EXISTS:
                        mode = "decoded-uncompressed"
                    else:
                        raise ValueError("Matching retail content needs unsupported re-encoding")
                    choices[index] = {"archive": path.name, "mode": mode}
        entries = []
        for identity, (slot, index) in sorted(patch.identities.items(), key=lambda x: x[1][1]):
            category = RETAIL if index in choices else CHANGED if matches[index] else UNMATCHED
            offset, packed, size, flags = patch.blocks[index]
            entries.append({"originalBlock": index, "identity": list(identity),
                            "lookupSlot": slot, "offset": offset, "packedBytes": packed,
                            "bytes": size, "flags": flags, "rawSha256": raw_hashes[index],
                            "contentSha256": sha(decoded[index]), "category": category,
                            "retailSource": choices.get(index), "pathMatches": matches[index]})
        manifest = {"schema": 1, "format": "d2-chinese-mpq-split-v1",
                    "sourceMpq": {"sha256": source_hash, "bytes": len(original)},
                    "layout": {"file": "archive-layout.bin", "bytes": len(layout),
                               "sha256": sha(layout)},
                    "classificationBasis": "Same MPQ hash/locale identity and decoded bytes. "
                        "Unmatched is not a declaration of authorship or redistribution permission.",
                    "legalPermissionsCertified": False, "entries": entries, "artifacts": {}}
        for category, name in OUTPUTS.items():
            subset = [e for e in entries if e["category"] == category]
            if not subset:
                continue
            write_overlay(patch, {e["originalBlock"] for e in subset}, stage / name)
            verify_overlay(storm, stage / name, subset)
            manifest["artifacts"][category] = {"file": name, "entries": len(subset),
                                              "sha256": file_sha(stage / name),
                                              "bytes": (stage / name).stat().st_size}
        counts = {k: sum(e["category"] == k for e in entries)
                  for k in (RETAIL, CHANGED, UNMATCHED)}
        manifest["counts"] = counts
        json_write(stage / "split-manifest.json", manifest)
        json_write(stage / "retail-copy-plan.json", {
            "note": "References and hashes only; these game bytes are not in the split overlays.",
            "entries": [e for e in entries if e["category"] == RETAIL]})
        shutil.copyfile(__file__, stage / "mpq_split.py")
        shutil.copyfile(storm.path, stage / "StormLib.dll")
        license_path = ROOT / "dist/Diablo II for RGDSplus/Ports/Diablo II for RGDSplus/licenses/MIT-StormLib.txt"
        if not license_path.is_file():
            raise FileNotFoundError("StormLib license is required for the helper bundle")
        shutil.copyfile(license_path, stage / "LICENSE-StormLib.txt")
        (stage / "Rebuild Chinese Patch.cmd").write_bytes(
            b'@echo off\r\npy -3 "%~dp0mpq_split.py" --stormlib "%~dp0StormLib.dll" rebuild --bundle "%~dp0." %*\r\n'
            b'if errorlevel 1 echo Rebuild failed. Read the error above.\r\npause\r\n')
        (stage / "README.zh-CN.txt").write_text(
            "中文 MPQ 技术拆分结果（未作分发授权认证）\n\n"
            f"正版相同资源 {counts[RETAIL]} 项：仅保存来源和哈希，由玩家从正版 MPQ 读取。\n"
            f"覆盖原有路径但内容不同 {counts[CHANGED]} 项：zh-CN-existing-path-changes.mpq。\n"
            f"在当前英文正版中未匹配路径 {counts[UNMATCHED]} 项：zh-CN-unmatched-candidates.mpq。\n"
            "后两组都需继续核对来源与授权；不能据此称为纯原创或可自由分发。\n"
            "这些分片是重组输入，不要直接替换掌机的 Patch_D2.mpq。\n\n"
            "本地重组需要 Windows x64、64 位 Python 3.10+ 和自己的受支持正版安装。\n"
            "可双击 Rebuild Chinese Patch.cmd，按提示填写正版目录和新的输出文件路径。\n"
            "也可运行：\n"
            'py -3 mpq_split.py --stormlib StormLib.dll rebuild --bundle . --source "正版目录" --output "新目录/Patch_D2.mpq"\n'
            "重组拒绝覆盖已有文件、写入正版安装目录或分片目录。源安装和分片只读。\n"
            "成功必须通过整个原 MPQ 的 SHA256；不是只检查文件数量。\n"
            "本次没有修改正式 ZIP、导入器、掌机或存档；ARM 内核拆分不在本步骤内。\n",
            encoding="utf-8")
        if file_sha(patch_path) != source_hash:
            raise ValueError("Source patch changed during splitting")
        # End all native archive handles before committing a complete bundle.
        stack.close()
        stage.rename(output)
        return {"output": str(output), "counts": counts, "sourceSha256": source_hash,
                "artifacts": manifest["artifacts"]}


def rebuild(storm, bundle, retail_dir, output):
    bundle = Path(bundle).resolve(strict=True)
    retail_dir = Path(retail_dir).resolve(strict=True)
    output = destination(output, (bundle, retail_dir))
    manifest = json.loads((bundle / "split-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("format") != "d2-chinese-mpq-split-v1":
        raise ValueError("Unsupported split manifest")
    if manifest["layout"]["file"] != "archive-layout.bin":
        raise ValueError("Unexpected archive layout path")
    layout = (bundle / "archive-layout.bin").read_bytes()
    if sha(layout) != manifest["layout"]["sha256"] or len(layout) != manifest["layout"]["bytes"]:
        raise ValueError("Damaged archive layout")
    total = manifest["sourceMpq"]["bytes"]
    if not 32 <= len(layout) <= total <= MASK:
        raise ValueError("Invalid reconstructed archive size")
    with ExitStack() as stack, tempfile.TemporaryDirectory(
            prefix=".d2-cn-rebuild-", dir=output.parent) as temporary:
        archives, overlays = {}, {}
        names = {p.name.lower(): p for p in retail_dir.glob("*.mpq")}
        for category, artifact in manifest["artifacts"].items():
            if category not in OUTPUTS or artifact["file"] != OUTPUTS[category]:
                raise ValueError("Unexpected overlay path")
            path = bundle / artifact["file"]
            if file_sha(path) != artifact["sha256"]:
                raise ValueError("Damaged split overlay: " + path.name)
            overlays[category] = stack.enter_context(Archive(storm, path))
        stage = Path(temporary) / "Patch_D2.mpq"
        previous_end = len(layout)
        with stage.open("xb") as stream:
            stream.write(layout)
            stream.truncate(total)
            for entry in sorted(manifest["entries"], key=lambda e: e["offset"]):
                identity = identity_for(entry)
                category = entry["category"]
                if category == RETAIL:
                    source = entry["retailSource"]
                    name = source["archive"]
                    if Path(name).name != name or "/" in name or "\\" in name:
                        raise ValueError("Invalid retail archive name")
                    if name.lower() not in archives:
                        if name.lower() not in names:
                            raise FileNotFoundError("Missing player archive: " + name)
                        archives[name.lower()] = stack.enter_context(Archive(storm, names[name.lower()]))
                    archive = archives[name.lower()]
                else:
                    if category not in overlays:
                        raise ValueError("Missing overlay category")
                    archive = overlays[category]
                if identity not in archive.identities:
                    raise ValueError("Required hash/locale identity missing")
                _, index = archive.identities[identity]
                if sha(archive.read(index)) != entry["contentSha256"]:
                    raise ValueError("Unsupported/damaged player resource or overlay")
                if category == RETAIL and entry["retailSource"]["mode"] == "decoded-uncompressed":
                    raw = archive.read(index)
                else:
                    if category == RETAIL and entry["retailSource"]["mode"] != "raw-copy":
                        raise ValueError("Unsupported retail reconstruction mode")
                    raw = archive.raw(index)
                if len(raw) != entry["packedBytes"] or sha(raw) != entry["rawSha256"]:
                    raise ValueError("Encoded resource differs; refusing an inexact rebuild")
                offset = entry["offset"]
                if offset < previous_end or offset + len(raw) > total:
                    raise ValueError("Overlapping/out-of-bounds reconstruction spans")
                stream.seek(offset)
                stream.write(raw)
                previous_end = offset + len(raw)
        if file_sha(stage) != manifest["sourceMpq"]["sha256"]:
            raise ValueError("Full reconstructed MPQ hash mismatch")
        with Archive(storm, stage) as rebuilt:
            if len(rebuilt.identities) != len(manifest["entries"]):
                raise ValueError("Reconstructed MPQ coverage mismatch")
            for entry in manifest["entries"]:
                _, index = rebuilt.identities[identity_for(entry)]
                if sha(rebuilt.read(index)) != entry["contentSha256"]:
                    raise ValueError("Reconstructed MPQ decoded verification failed")
        stack.close()
        stage.rename(output)
    return {"output": str(output), "sha256": file_sha(output),
            "entriesVerified": len(manifest["entries"]), "byteIdenticalToOriginal": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    adjacent = Path(__file__).with_name("StormLib.dll")
    parser.add_argument("--stormlib", type=Path,
                        default=adjacent if adjacent.exists() else DEFAULT_DLL)
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("split")
    command.add_argument("--patch", type=Path, required=True)
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command = subparsers.add_parser("rebuild")
    command.add_argument("--bundle", type=Path, required=True)
    command.add_argument("--source", type=Path)
    command.add_argument("--output", type=Path)
    args = parser.parse_args()
    storm = Storm(args.stormlib)
    if args.command == "split":
        result = split(storm, args.patch, args.source, args.output)
    else:
        if args.source is None:
            args.source = Path(input("Original Diablo II installation folder: ").strip().strip('"'))
        if args.output is None:
            args.output = Path(input("New output Patch_D2.mpq path (must not exist): ").strip().strip('"'))
        result = rebuild(storm, args.bundle, args.source, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
