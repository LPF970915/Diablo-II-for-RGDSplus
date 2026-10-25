#!/bin/sh
# Keep this bootstrap POSIX-compatible: some frontends invoke scripts with sh.
d2_boot_log="$0.boot.log"
if (umask 077; : >> "$d2_boot_log") 2>/dev/null; then
    exec >> "$d2_boot_log" 2>&1
else
    d2_boot_log="/tmp/diablo2-boot.log"
    exec >> "$d2_boot_log" 2>&1
fi
printf '\nDiablo II bootstrap: %s; script=%s; cwd=%s\n' "$(date)" "$0" "$PWD"
if [ -z "${BASH_VERSION:-}" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    fi
    echo 'Required interpreter missing: bash'
    exit 1
fi
set +o posix
set -eE
trap 'status=$?; printf "ERROR: exit=%s line=%s command=%s\n" "$status" "$LINENO" "$BASH_COMMAND" >&2' ERR
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Match PortMaster muOS control.txt: resolve the merged ROM view to a card.
case "$base/" in
    /mnt/union/*)
        relative=${base#/mnt/union}
        for card in /mnt/sdcard /mnt/mmc; do
            if [[ -f "$card$relative/${0##*/}" ]]; then
                base="$card$relative"
                break
            fi
        done ;;
esac
roots=("$base")
# ROM launchers may be organised into subfolders below ROMS.
ancestor=$base
while [[ "$ancestor" != / && -n "$ancestor" ]]; do
    if [[ ${ancestor##*/} == [Rr][Oo][Mm][Ss] ]]; then
        roots+=("${ancestor%/*}/ports")
        break
    fi
    ancestor=${ancestor%/*}
done
case "$base/" in
    /mnt/mmc/*) roots+=(/mnt/mmc/ports) ;;
    /mnt/sdcard/*) roots+=(/mnt/sdcard/ports) ;;
esac
port=
for candidate in "${roots[@]}"; do
    if [[ -f "$candidate/game-session.bash" ]]; then
        port=$(cd -- "$candidate" && pwd)
        break
    fi
done
if [[ -z "$port" ]]; then
    printf 'Diablo II: папка diablo2 не найдена. Проверены:\n' >&2
    printf '  %s/diablo2\n' "${roots[@]}" >&2
    exit 1
fi
printf 'Game directory: %s; game log: %s/log.txt\n' "$port" "$port"
if ! { exec >> "$port/log.txt"; }; then
    echo "Cannot write game log: $port/log.txt"
    exit 1
fi
exec 2>&1
printf '\nDiablo II launch: %s\n' "$(date -Iseconds)"
[[ ! -f "$port/port-env.conf" ]] || source "$port/port-env.conf"
source "$port/platform.bash"
d2_platform_setup "$base" "$port"
[[ $(uname -m) = aarch64 ]] || { echo 'This build requires aarch64 firmware with ARM32 support'; exit 1; }
for required in python3 mount umount; do
    command -v "$required" >/dev/null || { echo "Required firmware command missing: $required"; exit 1; }
done
lock=/tmp/diablo2-launch.lock
# A launcher that is killed outright -- SIGKILL from the frontend, a hard reset
# or a power loss -- never runs its EXIT trap, so the lock directory survives
# and blocks every later launch with "already starting or running". Record the
# owning pid and clear the lock as soon as that launcher is no longer alive.
lock_owner_alive() {
    local pid
    pid=$(cat "$lock/pid" 2>/dev/null) || return 1
    [[ -n $pid ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -qi diablo
}
release_lock() { rm -f "$lock/pid" 2>/dev/null; rmdir "$lock" 2>/dev/null; }
if [[ -d $lock ]] && ! lock_owner_alive; then
    echo 'Clearing stale launch lock: previous launcher is no longer running'
    release_lock
fi
mkdir "$lock" 2>/dev/null || { echo 'Diablo II is already starting or running'; exit 1; }
echo $$ > "$lock/pid"
trap release_lock EXIT
export D2_WINE_ROOT=/tmp/diablo2-wine
export D2_WINE_PREFIX=/tmp/diablo2-prefix
export D2_NATIVE_ROOT=/tmp/diablo2-native
mkdir -p "$D2_NATIVE_ROOT"
tar -xzf "$port/native-libs.tar.gz" -C "$D2_NATIVE_ROOT"
weston=/tmp/diablo2-weston
is_mounted() { grep -qs " $1 " /proc/mounts; }
mkdir -p "$D2_WINE_ROOT" "$D2_WINE_PREFIX" "$weston"
if [[ ! -f "$port/prefix.ext4" ]]; then
    # exFAT cannot hold Wine's symlinks. Keep its filesystem inside a file.
    # Never format an existing prefix image.
    [[ ! -e "$port/prefix.ext4.new" ]] || { echo 'Incomplete prefix image exists; inspect prefix.ext4.new'; exit 1; }
    python3 "$port/create-prefix.py" "$port"
fi
mapper_pid=
unmount_runtime() {
    is_mounted "$1" || return 0
    # A group termination can run nested cleanup traps concurrently. Let
    # owned Wine/Weston children release their mappings before unmounting.
    for attempt in {1..30}; do
        umount "$1" 2>/dev/null && return 0
        sleep 0.1
    done
    echo "Runtime still busy after cleanup: $1" >&2
    return 1
}
cleanup() {
    status=$?
    trap - EXIT
    [[ -z "$mapper_pid" ]] || kill "$mapper_pid" 2>/dev/null || true
    bash "$port/wine-run.bash" --server -k || true
    bash "$port/wine-run.bash" --server -w || true
    sync
    unmount_runtime "$D2_WINE_PREFIX" || true
    unmount_runtime "$D2_WINE_ROOT" || true
    unmount_runtime "$weston" || true
    release_lock || true
    exit "$status"
}
trap cleanup EXIT
is_mounted "$D2_WINE_ROOT" || mount -t squashfs -o loop,ro "$port/wine-armhf.runtime" "$D2_WINE_ROOT"
is_mounted "$D2_WINE_PREFIX" || mount -t ext4 -o loop,noatime "$port/prefix.ext4" "$D2_WINE_PREFIX"
is_mounted "$weston" || mount -t squashfs -o loop,ro "$D2_WESTON_IMAGE" "$weston"
export SDL_GAMECONTROLLERCONFIG_FILE="$controlfolder/gamecontrollerdb.txt"
export TEXTINPUTINTERACTIVE=Y
# -k enables Start + Select; match only the game, not this mapper's arguments.
# Controller and touch input are routed by the private game bridge.
mapper_pid=
cd "$port"
bash "$port/weston-session.bash" bash "$port/present-session.bash"
