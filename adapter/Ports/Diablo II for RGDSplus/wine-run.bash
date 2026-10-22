#!/bin/bash
set -eu
runtime=${D2_WINE_ROOT:-/tmp/diablo2-wine}
port=$(cd -- "$(dirname -- "$0")" && pwd)
export D2_WINE_ROOT="$runtime"
export D2_ARMHF_ROOT=${D2_ARMHF_ROOT:-/tmp/diablo2-armhf}
export D2_ARMHF_LOADER="$D2_ARMHF_ROOT/lib/ld-linux-armhf.so.3"
if [[ ! -x "$D2_ARMHF_LOADER" ]]; then
    mkdir -p "$D2_ARMHF_ROOT"
    tar -xzf "$port/armhf-libc.tar.gz" -C "$D2_ARMHF_ROOT"
fi
if [[ ! -f "$D2_ARMHF_ROOT/usr/lib/arm-linux-gnueabihf/alsa-lib/libasound_module_pcm_pulse.so" ]]; then
    tar -xzf "$port/armhf-audio.tar.gz" -C "$D2_ARMHF_ROOT"
fi
export ALSA_PLUGIN_DIR="$D2_ARMHF_ROOT/usr/lib/arm-linux-gnueabihf/alsa-lib"
cp "$port/alsa.conf" "$D2_ARMHF_ROOT/alsa.conf"
export ALSA_CONFIG_PATH="$D2_ARMHF_ROOT/alsa.conf"
if [[ ! -x "$runtime/usr/lib/wine/wine" ]]; then
    echo "Wine runtime is not mounted at $runtime" >&2
    exit 1
fi
# Keep firmware glibc: mixing Debian's older libc with KNULLI's loader is unsafe.
unset LD_PRELOAD
# Wine uses X11, not Weston's private Wayland socket. Keep its audio client
# on KNULLI's PipeWire server so hardware volume keys control the game too.
export XDG_RUNTIME_DIR=${D2_AUDIO_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-/run}}
# Prefer firmware ARM32 ALSA and its matching plugins on either firmware.
alsa_preload=
for libdir in /usr/lib32 /usr/lib/arm-linux-gnueabihf /lib32; do
    [[ -f "$libdir/libasound.so.2" ]] || continue
    alsa_preload="$libdir/libasound.so.2"
    [[ ! -d "$libdir/alsa-lib" ]] || export ALSA_PLUGIN_DIR="$libdir/alsa-lib"
    [[ ! -d "$libdir/spa-0.2" ]] || export SPA_PLUGIN_DIR="$libdir/spa-0.2"
    [[ ! -d "$libdir/pipewire-0.3" ]] || export PIPEWIRE_MODULE_DIR="$libdir/pipewire-0.3"
    break
done
export LD_LIBRARY_PATH="$D2_ARMHF_ROOT/lib/arm-linux-gnueabihf:$runtime/usr/lib/arm-linux-gnueabihf/wine:$runtime/usr/lib/arm-linux-gnueabihf:$runtime/usr/lib/arm-linux-gnueabihf/pulseaudio:$runtime/port-libs"
export WINEDLLPATH="$runtime/usr/lib/arm-linux-gnueabihf/wine"
export WINELOADER="$port/wine-loader.bash"
export WINESERVER="$port/wineserver.bash"
export WINEDATADIR="$runtime/usr/share/wine"
export WINEARCH=win32
export WINEDEBUG=${WINEDEBUG:--all}
export WINEDLLOVERRIDES="mscoree,mshtml="
export WINEPREFIX=${D2_WINE_PREFIX:-/tmp/diablo2-prefix}
export D2_SLEEPHACK=1
if [[ "${1:-}" = --server ]]; then
    shift
    exec env LD_PRELOAD="$alsa_preload" "$WINESERVER" "$@"
fi
port=$(cd -- "$(dirname -- "$0")" && pwd)

target=${1:-}
if [[ "$target" = *.exe.so ]]; then
    # This is a Winelib application, not a Windows image: readelf -d shows
    # NEEDED libwine.so.1 and only 11 undefined symbols, among them
    # __wine_main_argc/__wine_main_argv, and GetCommandLineA is defined right
    # here in this file at 0x12c690. wine 4.0 can start such applications --
    # wine_init has the wine_dlopen / wine_dlsym / wine_call_on_stack chain --
    # but it needs a running server and can fail with exit status 193:
    #     wine: Bad EXE format for Z:\roms\ports\diablo2\libd2game_sa_arm.exe.so
    set +e
    python3 "$port/linux32.py" "$alsa_preload" "$WINELOADER" "$@"
    status=$?
    set -e
    if [ "$status" = 193 ]; then
        # Keep a server alive: the ELF's initialisers talk to it, and the
        # transient one used by wineboot is long gone by now.
        env LD_PRELOAD="$alsa_preload" "$WINESERVER" -p >/dev/null 2>&1 || true
        # Run it again with loader tracing so the reason survives in the log.
        set +e
        LD_DEBUG=libs LD_DEBUG_OUTPUT="$port/dlopen-debug" \
            python3 "$port/linux32.py" "$alsa_preload" "$WINELOADER" "$@"
        status=$?
        set -e
        rm -f "$port"/dlopen-debug.[0-9]*.keep 2>/dev/null || true
    fi
    if [ "$status" = 193 ]; then
        # Last resort: start the ELF through the dynamic loader. The server set
        # up above stays available. This loses wine_init, so it usually crashes.
        echo 'wine loader cannot start this Winelib ELF; trying the dynamic loader' >&2
        set +e
        python3 "$port/linux32.py" "$alsa_preload" "$D2_ARMHF_LOADER" \
            --library-path "$runtime/usr/lib/arm-linux-gnueabihf/wine:$runtime/usr/lib/arm-linux-gnueabihf:$runtime/port-libs:${D2_ARMHF_LIBRARY_PATH:-/usr/lib32:/lib32}" "$@"
        status=$?
        set -e
    fi
    exit "$status"
fi

exec python3 "$port/linux32.py" "$alsa_preload" "$WINELOADER" "$@"
