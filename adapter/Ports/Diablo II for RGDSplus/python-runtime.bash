#!/bin/bash
# Source this before any Python helper. Never change the firmware interpreter.
d2_python_archive="$payload/runtime/offline/python-aarch64.tar.gz"
d2_python_sha=a2364356a17f63de74120a55d5af1f8ae56b8e700c9d43f478ba90e2f543f3a6
[[ $(sha256sum "$d2_python_archive" | cut -d ' ' -f1) == "$d2_python_sha" ]] || {
    echo 'Bundled Python archive missing or damaged; reinstall the adapter files.' >&2
    exit 1
}
d2_python_root=/tmp/diablo2-python-a2364356a17f
if [[ ! -x "$d2_python_root/bin/python3" || $(cat "$d2_python_root/.archive-sha256" 2>/dev/null) != "$d2_python_sha" ]]; then
    [[ ! -e "$d2_python_root" ]] || { echo 'Unexpected Python runtime cache; reboot before retrying.' >&2; exit 1; }
    d2_python_stage=$(mktemp -d /tmp/diablo2-python-stage.XXXXXX)
    tar -xzf "$d2_python_archive" -C "$d2_python_stage"
    printf '%s\n' "$d2_python_sha" > "$d2_python_stage/python/.archive-sha256"
    mv "$d2_python_stage/python" "$d2_python_root"
    rmdir "$d2_python_stage"
fi
unset PYTHONHOME PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1
export PATH="$d2_python_root/bin:$PATH"
python3 -I -c 'import ast, ctypes, hashlib, json, zlib; compile("x=1", "preflight", "exec"); print("PYTHON_RUNTIME_READY: isolated bundled interpreter")'
