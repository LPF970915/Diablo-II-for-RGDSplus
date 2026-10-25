#!/bin/bash
set -eu
port=$(cd -- "$(dirname -- "$0")" && pwd)
weston=${D2_WESTON_ROOT:-/tmp/diablo2-weston}
bridge= game=
input_ready=$(mktemp /tmp/diablo2-input-ready.XXXXXX)
export D2_INPUT_READY="$input_ready"
touch_mode_path=/sys/class/anbernic_misc/tpctrl
touch_mode_previous=
touch_mode_changed=0
restore_touch_mode() {
    [[ $touch_mode_changed == 1 ]] || return 0
    current=$(cat "$touch_mode_path" 2>/dev/null || true)
    if [[ "$current" == 0 ]]; then
        printf '%s\n' "$touch_mode_previous" > "$touch_mode_path" 2>/dev/null || true
        echo "TOUCH_MODE: restored=$(cat "$touch_mode_path" 2>/dev/null || true)"
    fi
}
cleanup() {
    status=$?
    trap - EXIT
    [[ -z "$game" ]] || kill "$game" 2>/dev/null || true
    [[ -z "$bridge" ]] || kill "$bridge" 2>/dev/null || true
    [[ -z "$bridge" ]] || wait "$bridge" 2>/dev/null || true
    rm -f -- "$input_ready"
    restore_touch_mode
    exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM HUP
trap 'exit 130' INT
# If another Port left the panel in mode 1, the evdev node reports no
# contacts at all. Request the firmware's reporting mode 0 only for this
# game session, and restore the previous value on exit. This is not a
# persistent system touch-policy change and never creates a virtual input
# device.
if [[ -r "$touch_mode_path" ]]; then
    touch_mode_previous=$(cat "$touch_mode_path" 2>/dev/null || true)
    case "$touch_mode_previous" in
        0) ;;
        1)
            if printf '0\n' > "$touch_mode_path" 2>/dev/null && [[ $(cat "$touch_mode_path" 2>/dev/null) == 0 ]]; then
                touch_mode_changed=1
                echo "TOUCH_MODE: previous=$touch_mode_previous requested=0"
            else
                echo "TOUCH_MODE: cannot request 0; previous=$touch_mode_previous" >&2
            fi
            ;;
    esac
fi
# Keep the firmware touch policy untouched apart from the session-scoped
# mode above. The private bridge grabs the evdev node after it starts, and
# LowerTouch.prepare() discards any contact held during game loading.
LD_LIBRARY_PATH="$weston/lib_aarch64" SDL_VIDEODRIVER="${D2_SDL_VIDEO_DRIVER:-mali}" python3 "$port/display.py" &
bridge=$!
for attempt in {1..300}; do
    kill -0 "$bridge" 2>/dev/null || { echo 'Display/input initialization failed'; exit 1; }
    [[ $(cat "$input_ready") != "$bridge" ]] || break
    sleep 0.1
done
[[ $(cat "$input_ready") == "$bridge" ]] || { echo 'Display/input readiness timed out'; exit 1; }
echo "INPUT_READY: bridge=$bridge before native game launch"
bash "$port/game-session.bash" &
game=$!
while kill -0 "$game" 2>/dev/null; do
    kill -0 "$bridge" 2>/dev/null || { echo 'Display bridge exited'; exit 1; }
    sleep 0.2
done
set +e
wait "$game"
status=$?
set -e
printf "NATIVE_GAME_EXIT: status=%s time=%s\n" "$status" "$(date -Iseconds)"
game=
exit "$status"
