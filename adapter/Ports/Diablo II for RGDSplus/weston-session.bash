#!/bin/bash
# KNULLI H700 Westonpack adapter. Does not source PortMaster control.txt.
set -eu
weston=${D2_WESTON_ROOT:-/tmp/diablo2-weston}
port=$(cd -- "$(dirname -- "$0")" && pwd)
app_cwd=$PWD
ulimit -c 0
active_process() {
    for pid in $(pgrep -x "$1" || true); do
        [[ $(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null) = Z ]] || return 0
    done
    return 1
}
if active_process wp_weston || active_process seatd || active_process Xwayland || active_process Xorg; then
    echo 'Another compositor/session is active; refusing to replace it.' >&2
    exit 1
fi
if [[ -f /tmp/.X0-lock ]]; then
    xpid=$(tr -d '[:space:]' < /tmp/.X0-lock)
    if [[ "$xpid" =~ ^[0-9]+$ ]] && kill -0 "$xpid" 2>/dev/null; then
        echo 'An X server owns display :0' >&2
        exit 1
    fi
fi
# Never remove or change shared system X11 state. If the private display number
# is occupied, fail closed and leave the owner untouched.
if [[ -e /tmp/.X0-lock || -e /tmp/.X11-unix/X0 ]]; then
    echo 'Shared X11 display :0 is occupied; refusing to touch it.' >&2
    exit 1
fi
x11_socket_dir=/tmp/.X11-unix
x11_socket_dir_created=0
xdg_runtime_dir=
export LIBSEAT_BACKEND=noop
export WESTON_DATA_DIR="$weston/data"
export WESTON_LIBEXEC_DIR="$weston/libexec"
export XKB_CONFIG_ROOT="$weston/share/xkb"
export WESTON_MODULE_MAP="drm-backend.so=$weston/lib_aarch64/libweston-14/drm-backend.so;headless-backend.so=$weston/lib_aarch64/libweston-14/headless-backend.so;gl-renderer.so=$weston/lib_aarch64/libweston-14/gl-renderer.so;kiosk-shell.so=$weston/lib_aarch64/weston/kiosk-shell.so;xwayland.so=$weston/lib_aarch64/libweston-14/xwayland.so;"
export XWAYLAND_LD_LIBRARY_PATH="$weston/lib_aarch64/graphics/mesa_x11_stub:$D2_NATIVE_ROOT/usr/lib/aarch64-linux-gnu:$weston/lib_aarch64"
weston_pid=
cleanup() {
    status=$?
    trap - EXIT
    [[ -z "$weston_pid" ]] || kill "$weston_pid" 2>/dev/null || true
    if [[ -n "$weston_pid" ]]; then
        for attempt in {1..20}; do
            kill -0 "$weston_pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL "$weston_pid" 2>/dev/null || true
    fi
    [[ -z "$weston_pid" ]] || wait "$weston_pid" 2>/dev/null || true
    [[ -z "$xdg_runtime_dir" ]] || rmdir "$xdg_runtime_dir" 2>/dev/null || true
    if [[ $x11_socket_dir_created == 1 ]]; then
        rmdir "$x11_socket_dir" 2>/dev/null || true
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
if [[ ! -e "$x11_socket_dir" ]]; then
    (umask 077 && mkdir "$x11_socket_dir") || {
        echo 'Cannot create the private X11 socket directory for this game session.' >&2
        exit 1
    }
    x11_socket_dir_created=1
fi
[[ -d "$x11_socket_dir" && -w "$x11_socket_dir" && -x "$x11_socket_dir" ]] || {
    echo 'X11 socket directory is unavailable or not writable; leaving existing state untouched.' >&2
    exit 1
}
xdg_runtime_dir="/tmp/diablo2-xdg-${UID}-$$"
mkdir "$xdg_runtime_dir"
chmod 700 "$xdg_runtime_dir"
export XDG_RUNTIME_DIR="$xdg_runtime_dir"
cd "$weston"
LD_LIBRARY_PATH="$D2_NATIVE_ROOT/usr/lib/aarch64-linux-gnu:$weston/lib_aarch64" "$weston/wp_weston" \
    -c "$port/weston.ini" -B headless --use-pixman --width=800 --height=600 \
    --shell=kiosk-shell.so -i0 -Sdiablo2-wayland --xwayland &
weston_pid=$!
for attempt in {1..200}; do
    [[ ! -S /tmp/.X11-unix/X0 ]] || break
    kill -0 "$weston_pid" || { echo 'Weston exited before X11 became available'; exit 1; }
    sleep 0.1
done
[[ -S /tmp/.X11-unix/X0 ]] || { echo 'Timed out waiting for Xwayland'; exit 1; }
export DISPLAY=:0
export WAYLAND_DISPLAY=diablo2-wayland
cd "$app_cwd"
"$@"
