#!/bin/bash
# Port-local setup only: do not source firmware-modifying PortMaster control.txt.
d2_platform_setup() {
    local base=$1 port=$2 candidate mapper os_name= preferred_pm
    if [[ -r /etc/os-release ]]; then
        os_name=$(grep -E '^(OS_NAME|NAME|ID)=' /etc/os-release | tr '[:upper:]' '[:lower:]')
    fi
    if [[ -z ${D2_PLATFORM:-} ]]; then
        case "$os_name" in
            *muos*|*mustard*) D2_PLATFORM=muos ;;
            *knulli*|*batocera*) D2_PLATFORM=knulli ;;
            *)
                if [[ -d /opt/muos || -d /mnt/mmc/MUOS ]]; then
                    D2_PLATFORM=muos
                else
                    echo 'Unsupported firmware: this port targets KNULLI and muOS on H700.'
                    return 1
                fi ;;
        esac
    fi
    case "$D2_PLATFORM" in knulli|muos|rgdsplus) ;; *) echo "Unknown D2_PLATFORM: $D2_PLATFORM"; return 1 ;; esac
    export D2_PLATFORM
    if [[ "$D2_PLATFORM" = rgdsplus ]]; then
        preferred_pm=/mnt/ports/PortMaster
    elif [[ "$D2_PLATFORM" = knulli ]]; then
        preferred_pm=/userdata/system/.local/share/PortMaster
    else
        preferred_pm=/mnt/mmc/MUOS/PortMaster
    fi
    local candidates=(
        "${D2_PORTMASTER_DIR:-}" "$preferred_pm" "$base/PortMaster" "${port%/*}/PortMaster"
        /mnt/mmc/MUOS/PortMaster /mnt/mmc/ports/PortMaster
        /mnt/sdcard/MUOS/PortMaster /mnt/sdcard/ports/PortMaster
        /opt/muos/PortMaster /opt/system/Tools/PortMaster /opt/tools/PortMaster
        "${XDG_DATA_HOME:-${HOME:-/tmp}/.local/share}/PortMaster"
        /userdata/system/.local/share/PortMaster /roms/ports/PortMaster
        /roms2/ports/PortMaster /storage/.config/PortMaster
    )
    controlfolder=
    for candidate in "${candidates[@]}"; do
        [[ -n "$candidate" && -f "$candidate/gamecontrollerdb.txt" ]] || continue
        for mapper in gptokeyb gptokeyb.aarch64; do
            [[ -x "$candidate/$mapper" ]] || continue
            controlfolder=$candidate
            export D2_GPTOKEYB="$candidate/$mapper"
            break 2
        done
    done
    [[ -n "$controlfolder" ]] || { echo 'PortMaster gptokeyb/gamecontrollerdb.txt not found'; return 1; }
    if [[ -z ${D2_WESTON_IMAGE:-} && -f "$port/weston.runtime" ]]; then
        D2_WESTON_IMAGE="$port/weston.runtime"
    fi
    if [[ -z ${D2_WESTON_IMAGE:-} ]]; then
        for candidate in "$controlfolder/libs" "$controlfolder/libs.aarch64"; do
            if [[ -f "$candidate/weston_pkg_0.2.squashfs" ]]; then
                D2_WESTON_IMAGE="$candidate/weston_pkg_0.2.squashfs"
                break
            fi
        done
    fi
    [[ -f ${D2_WESTON_IMAGE:-} ]] || { echo 'Install the PortMaster Westonpack 0.2 runtime'; return 1; }
    export D2_WESTON_IMAGE
    # Weston gets a private XDG_RUNTIME_DIR later. Save the firmware audio path.
    if [[ "$D2_PLATFORM" = knulli ]]; then
        export D2_AUDIO_RUNTIME_DIR=${D2_AUDIO_RUNTIME_DIR:-/var/run}
    else
        export D2_AUDIO_RUNTIME_DIR=${D2_AUDIO_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-/run}}
    fi
    export D2_ARMHF_LIBRARY_PATH=${D2_ARMHF_LIBRARY_PATH:-/usr/lib32:/lib32:/usr/lib/arm-linux-gnueabihf:/lib/arm-linux-gnueabihf}
    printf 'Platform: %s; PortMaster: %s; game: %s\n' "$D2_PLATFORM" "$controlfolder" "$port"
}
