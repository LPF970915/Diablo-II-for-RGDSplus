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
# 上一个会话若以 root 身份跑过 weston（SSH 自测、别的端口的 weston 等），这两个
# 文件会归 root 所有。/tmp 带 sticky 位，ark 既不是文件属主也不是目录属主 →
# rm 直接 EPERM；本脚本开着 `set -e`，于是在这里静默退出，表现为"启动即闪退"，
# 而日志里一行报错都没有。用 sudo 兜底删掉。
rm -f /tmp/.X11-unix/X0 /tmp/.X0-lock 2>/dev/null || true
if [[ -e /tmp/.X11-unix/X0 || -e /tmp/.X0-lock ]]; then
    /usr/bin/sudo -n rm -f /tmp/.X11-unix/X0 /tmp/.X0-lock 2>/dev/null || true
fi
export XDG_RUNTIME_DIR=/tmp/diablo2-xdg
mkdir -p "$XDG_RUNTIME_DIR" /tmp/.X11-unix
# 同理：root 重建过的 .X11-unix 会变成 0755 root，ark 无法在里面建 X0 socket。
chmod 1777 /tmp/.X11-unix 2>/dev/null \
    || /usr/bin/sudo -n chmod 1777 /tmp/.X11-unix 2>/dev/null || true
chmod 700 "$XDG_RUNTIME_DIR"
# ---- libseat / seatd ----
# weston 默认走 libseat 的 builtin seatd：它必须先打开当前 VT 才能激活 seat。
# 本机 EmulationStation 由 systemd 启动，没有控制终端（tty_nr=0），于是报
#     Could not open target tty: Permission denied
#     Could open device: client is not active
#     fatal: failed to create compositor backend
# 整个 compositor 起不来 → 游戏秒退。
# noop 后端完全不碰 VT，直接 open() 输入设备（ark 属于 input 组，权限足够）。
# 实测：event0 / event3 / event4(Fake Keyboard) 均正常接管，xwayland.so 正常加载，
# /tmp/.X11-unix/X0 正常创建。有控制终端时用它同样安全。
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
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
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
