#!/bin/bash
set -eu
unset LD_PRELOAD
exec "$D2_ARMHF_LOADER" --library-path "$LD_LIBRARY_PATH" "$D2_WINE_ROOT/usr/lib/wine/wine" "$@"
