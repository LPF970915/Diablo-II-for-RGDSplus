#!/usr/bin/env python3
"""Run ARM32 Wine with the personality used by util-linux setarch linux32 -L."""
import ctypes
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
libc.personality.argtypes = [ctypes.c_ulong]
libc.personality.restype = ctypes.c_int
# Linux UAPI: PER_LINUX32 | ADDR_COMPAT_LAYOUT.
if libc.personality(0x0008 | 0x0200000) == -1:
    error = ctypes.get_errno()
    sys.exit(f'Cannot set Wine process personality: {os.strerror(error)}')
env = dict(os.environ, LD_PRELOAD=sys.argv[1])
os.execvpe(sys.argv[2], sys.argv[2:], env)
