#!/bin/bash
set -euo pipefail
payload=$(cd -- "$(dirname -- "$0")" && pwd)
work=${D2_UI_WORK_DIR:-/tmp/diablo2-classic-controller}
export D2_DIRECT_MOVE=${D2_DIRECT_MOVE:-1}
export D2_WORLD_CANVAS=${D2_WORLD_CANVAS:-1}
export D2_INDEXED_FRAME=${D2_INDEXED_FRAME:-1}
export D2_WORLD_FRAME=/tmp/d2-classic-world.bin
export D2_STICK_FRAME=/tmp/d2-classic-stick.bin
export D2_COMBAT_STATUS=/tmp/d2-classic-combat.bin
export D2_UI_STATUS=/tmp/d2-classic-ui.bin
export D2_GUI_STATUS=/tmp/d2-classic-gui.bin
export D2_SAVE_DIR="$payload/saves"
export D2_WORLD_PROTOTYPE=1
export D2_QA_INPUT=0
export D2_FRONTEND_ASSETS="$payload/private-assets"
export D2_FRONTEND_REPORT=/tmp/d2-frontend-state.json

mkdir -p "$payload/logs"
exec >> "$payload/logs/launcher.log" 2>&1
printf '\nDiablo II classic controller preflight: %s\n' "$(date -Iseconds)"
python3 "$payload/audio_preflight.py"

[[ -d "$payload/gamedata" && -f "$payload/gamedata/Patch_D2.mpq" ]] || { echo 'Imported game resources are missing; run Import Game Assets.cmd first.'; exit 1; }
[[ -f "$payload/gamedata/resource-manifest.json" ]] || { echo 'Imported resource manifest is missing; run Import Game Assets.cmd from this package.'; exit 1; }
python3 "$payload/verify-resources.py" "$payload/gamedata" ${D2_VERIFY_RESOURCES:+--full}
python3 - "$payload/gamedata/resource-manifest.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding='utf-8-sig') as stream:
    manifest = json.load(stream)
profile = str(manifest.get('profile', ''))
if not profile.startswith('retail-enUS-1.14b'):
    raise SystemExit('Classic controller requires retail enUS 1.14b imported resources; found: ' + profile)
PY
python3 "$payload/verify-installation.py" "$payload"
[[ ! -d /tmp/diablo2-launch.lock ]] || { echo 'Exit the current Diablo II session first.'; exit 1; }
mkdir -p "$work" "$payload/saves"
python3 "$payload/create-prefix.py" "$payload"
runtime_files=(platform.bash wine-run.bash wine-loader.bash wineserver.bash
    linux32.py clear-exec-stack.py create-prefix.py prefix-empty.ext4.gz
    weston-session.bash weston.ini gptokeyb-d2 alsa.conf port-env.conf bin
    libd2game_sa_arm.exe.so)
adapter_files=(gamedata prefix.ext4 saves display.py touch.py joystick.py combat.py
    frontend_panels.py ui_controller.py ui_navigation.py indexed_display.py indexed_gpu.so controller-font.bin
    controller-layout.json retail_mpq.so touch_keyboard.py
    present-session.bash game-session.bash world_probe.so)
offline_files=(wine-armhf.runtime weston.runtime armhf-libc.tar.gz armhf-audio.tar.gz native-libs.tar.gz)
for name in "${runtime_files[@]}" "${adapter_files[@]}"; do
    [[ -e "$payload/$name" ]] || { echo "Missing runtime support file: $name"; exit 1; }
    ln -sfnT "$payload/$name" "$work/$name"
done
for name in "${offline_files[@]}"; do
    [[ -f "$payload/runtime/offline/$name" ]] || { echo "Missing offline runtime: $name"; exit 1; }
    ln -sfnT "$payload/runtime/offline/$name" "$work/$name"
done
ln -sfnT "$payload/launch-runtime.bash" "$work/launch.bash"
ln -sfnT "$payload/diablo2-direct.gptk" "$work/diablo2.gptk"
rm -f -- "$D2_WORLD_FRAME" "$D2_STICK_FRAME" "$D2_COMBAT_STATUS" "$D2_UI_STATUS" "$D2_GUI_STATUS"

# The runtime launcher is copied from the tested release package. This script
# only selects the local resources and then enters that private runtime.
exec bash "$work/launch.bash"
