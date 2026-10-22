#!/bin/bash
set -eu
port=$(cd -- "$(dirname -- "$0")" && pwd)
wine="$port/wine-run.bash"
prefix=${D2_WINE_PREFIX:-/tmp/diablo2-prefix}
cd "$port/gamedata"
if [[ ! -f "$prefix/.diablo2-configured-v2" ]]; then
    "$wine" wineboot.exe -u
    "$wine" reg.exe add 'HKCU\Software\Wine\Direct3D' /v DirectDrawRenderer /d gdi /f
    "$wine" reg.exe add 'HKCU\Software\Wine\Drivers' /v Audio /d pulse /f
    "$wine" reg.exe add 'HKCU\Software\Wine\X11 Driver' /v Managed /d N /f
    "$wine" reg.exe add 'HKCU\Software\Wine\Explorer' /v Desktop /d DiabloII /f
    "$wine" reg.exe add 'HKCU\Software\Wine\Explorer\Desktops' /v DiabloII /d 800x600 /f
    touch "$prefix/.diablo2-configured-v2"
fi
# Set after wineboot, on every run. The persistent path is supplied by this
# entry and never points at the old prototype or single-screen saves.
mkdir -p "$D2_SAVE_DIR"
save_path="Z:$(printf '%s' "$D2_SAVE_DIR" | sed 's,/,\\,g')"
"$wine" reg.exe add 'HKCU\Software\Blizzard Entertainment\Diablo II' /v 'Save Path' /d "$save_path" /f
"$wine" reg.exe add 'HKCU\Software\Wine\Drivers' /v Audio /d pulse /f
stage=${D2_STAGE_DIR:-/tmp/diablo2-bin}
mkdir -p "$stage"
cp -f "$port/libd2game_sa_arm.exe.so" "$stage/libd2game_sa_arm.exe.so"
python3 "$port/clear-exec-stack.py" "$stage/libd2game_sa_arm.exe.so"
# Use the imported original base MPQs plus the bundled, checked Chinese
# Patch_D2.mpq. No loose data tree or PC executable is loaded.
exec "$wine" "$stage/libd2game_sa_arm.exe.so"
