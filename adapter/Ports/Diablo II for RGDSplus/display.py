#!/usr/bin/env python3
"""Present the largest mapped X11 window through KNULLI's native SDL2 driver."""
import ctypes as C
import os
from pathlib import Path
import signal
import time
import mmap
import struct
import platform
from touch import LowerTouch
from joystick import LeftStick


class WorldFrames:
    """Read both render targets from one seqlock-protected game frame."""
    plane_size = 1024 * 768 * 4
    busy = object()

    def __init__(self):
        self.mapping = None
        self.upper = C.create_string_buffer(self.plane_size)
        self.lower = C.create_string_buffer(self.plane_size)
        self.cursor_item = False
        self.movement_blocked = True
        self.movement_rearm = True
        self.selected_target=0; self.target_health=0
        self.ui_flags=0
        self.sequence = None

    def is_current(self):
        if self.mapping is not None and getattr(self,'version',None) in (3,4):
            offset=128+4*self.plane_size+((self.sequence//2)&1)*8
            return struct.unpack_from('<I',self.mapping,offset)[0]==self.sequence
        return self.mapping is not None and struct.unpack_from('<I',self.mapping,8)[0] == self.sequence

    def read(self, direct=False):
        # Direct consumers must validate is_current() after copying/uploading
        # both planes and before presenting either. This lets SDL upload from
        # the mapped bank without an intermediate pair of CPU buffers.
        if self.mapping is None:
            try:
                with open(os.environ['D2_WORLD_FRAME'], 'r+b') as stream:
                    self.mapping_size = os.fstat(stream.fileno()).st_size
                    if self.mapping_size not in (128 + 2 * self.plane_size,128 + 4 * self.plane_size,144+4*self.plane_size,2192+4*self.plane_size):
                        return None
                    self.mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_WRITE)
                    # Borrow the mapped address only; do not retain an exported
                    # Python buffer or allocate two temporary 1.2 MB byte strings.
                    # The reader never writes to the mapping.
                    self.address = C.addressof(C.c_char.from_buffer(self.mapping))
            except (KeyError, OSError):
                return None
        for attempt in range(3):
            magic, version, sequence, width, height = struct.unpack_from('<5I', self.mapping)
            timestamp = struct.unpack_from('<Q', self.mapping, 32)[0]
            if magic != 0x44325750 or version not in (1,2,3,4):
                return None
            if self.mapping_size != 128 + (4 if version >= 2 else 2) * self.plane_size + (2064 if version==4 else 16 if version==3 else 0):
                return None
            if time.monotonic_ns() - timestamp > 2_000_000_000:
                return None
            if sequence & 1:
                continue
            if sequence == self.sequence:
                return self.busy
            if not (320 <= width <= 1024 and 400 <= height <= 768):
                return None
            size = width * height * (1 if version==4 else 4)
            bank = ((sequence // 2) & 1) * 2 * self.plane_size if version >= 2 else 0
            start = 128 + bank + self.plane_size
            if not direct:
                C.memmove(self.upper, self.address + 128 + bank, size)
                C.memmove(self.lower, self.address + start, size)
            cursor_item = bool(struct.unpack_from('<I', self.mapping, 72)[0])
            movement_flags = struct.unpack_from('<I', self.mapping, 76)[0]
            selected_target,target_health=struct.unpack_from('<2I',self.mapping,116)
            if struct.unpack_from('<I', self.mapping, 8)[0] == sequence:
                self.cursor_item = cursor_item
                self.sequence = sequence
                self.version = version
                self.palette = self.address+144+4*self.plane_size+((sequence//2)&1)*1024 if version==4 else None
                self.movement_blocked = bool(movement_flags & 1)
                self.ui_flags=movement_flags
                self.movement_rearm = bool(movement_flags & 2)
                self.selected_target=selected_target; self.target_health=min(1000,target_health)
                planes = (self.address+128+bank,self.address+start) if direct else (self.upper,self.lower)
                return width, height, *planes
        # A frame being written is not a scene exit. Keep the displayed pair;
        # otherwise odd sequences alternate the lower panel with black frames.
        return self.busy

    def wait(self):
        # Shared publication wakes the display immediately. Bounded waits keep
        # input responsive while loading or paused; no private futex flag.
        number={'aarch64':98,'x86_64':202}.get(platform.machine().lower())
        if self.mapping is None or os.name!='posix' or number is None:
            time.sleep(1/60);return
        if not hasattr(self,'libc'):
            self.libc=C.CDLL(None);self.libc.syscall.restype=C.c_long
        class Timeout(C.Structure):
            _fields_=[('seconds',C.c_long),('nanoseconds',C.c_long)]
        timeout=Timeout(0,16_000_000)
        expected=struct.unpack_from('<I',self.mapping,8)[0]
        if expected!=self.sequence:return
        self.libc.syscall(C.c_long(number),C.c_void_p(self.address+8),C.c_int(0),C.c_uint(expected),C.byref(timeout),C.c_void_p(0),C.c_uint(0))


class Attributes(C.Structure):
    _fields_ = [(n, C.c_int) for n in ('x', 'y', 'width', 'height', 'border_width', 'depth')] + [
        ('visual', C.c_void_p), ('root', C.c_ulong), ('class_', C.c_int),
        ('bit_gravity', C.c_int), ('win_gravity', C.c_int), ('backing_store', C.c_int),
        ('backing_planes', C.c_ulong), ('backing_pixel', C.c_ulong), ('save_under', C.c_int),
        ('colormap', C.c_ulong), ('map_installed', C.c_int), ('map_state', C.c_int),
        ('all_event_masks', C.c_long), ('your_event_mask', C.c_long),
        ('do_not_propagate_mask', C.c_long), ('override_redirect', C.c_int), ('screen', C.c_void_p)]


class XImage(C.Structure):
    _fields_ = [(n, C.c_int) for n in ('width', 'height', 'xoffset', 'format')] + [
        ('data', C.c_void_p)] + [(n, C.c_int) for n in (
        'byte_order', 'bitmap_unit', 'bitmap_bit_order', 'bitmap_pad', 'depth',
        'bytes_per_line', 'bits_per_pixel')] + [
        ('red_mask', C.c_ulong), ('green_mask', C.c_ulong), ('blue_mask', C.c_ulong),
        ('obdata', C.c_void_p), ('functions', C.c_void_p * 6)]


class Rect(C.Structure):
    _fields_ = [(name, C.c_int) for name in ('x', 'y', 'w', 'h')]

class RendererInfo(C.Structure):
    _fields_ = [('name',C.c_char_p),('flags',C.c_uint32),('count',C.c_uint32),
                ('formats',C.c_uint32*16),('max_width',C.c_int),('max_height',C.c_int)]

def bind(lib, name, result, args):
    func = getattr(lib, name)
    func.restype, func.argtypes = result, args
    return func


def native_frame_renderer(size, upper, lower):
    return upper if size == (640, 480) else lower or upper


def present_native_frame(sdl, upper, lower, texture, destination, size, ui, frontend=None):
    selected = native_frame_renderer(size, upper, lower)
    for panel in (upper, lower):
        if panel:
            sdl.SDL_SetRenderDrawColor(panel, 0, 0, 0, 255)
            sdl.SDL_RenderClear(panel)
    sdl.SDL_RenderCopy(selected, texture, None, C.byref(destination))
    if frontend and size == (800, 600):
        frontend.draw()
    if ui and size != (640, 480):
        ui.draw(sdl, selected, Rect)
    for panel in (upper, lower):
        if panel:
            sdl.SDL_RenderPresent(panel)


def main():
    weston = Path(os.environ.get('D2_WESTON_ROOT', '/tmp/diablo2-weston'))
    x = C.CDLL(str(weston / 'lib_aarch64/libX11.so.6'))
    s = None
    for name in (os.environ.get('D2_SDL_LIBRARY'), '/usr/lib/libSDL2.so',
                 '/usr/lib/libSDL2-2.0.so.0',
                 '/usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0', 'libSDL2-2.0.so.0'):
        if name:
            try:
                s = C.CDLL(name)
                break
            except OSError:
                pass
    if s is None:
        raise RuntimeError('Native SDL2 library not found on this firmware')
    ptr, integer, ulong = C.c_void_p, C.c_int, C.c_ulong
    bind(x, 'XOpenDisplay', ptr, [C.c_char_p])
    bind(x, 'XDefaultRootWindow', ulong, [ptr])
    bind(x, 'XQueryTree', integer, [ptr, ulong, C.POINTER(ulong), C.POINTER(ulong), C.POINTER(C.POINTER(ulong)), C.POINTER(C.c_uint)])
    bind(x, 'XGetWindowAttributes', integer, [ptr, ulong, C.POINTER(Attributes)])
    bind(x, 'XTranslateCoordinates', integer, [ptr, ulong, ulong, integer, integer,
                                               C.POINTER(integer), C.POINTER(integer), C.POINTER(ulong)])
    bind(x, 'XGetImage', C.POINTER(XImage), [ptr, ulong, integer, integer, C.c_uint, C.c_uint, ulong, integer])
    bind(x, 'XDestroyImage', integer, [C.POINTER(XImage)])
    bind(x, 'XFree', integer, [ptr])
    bind(x, 'XCloseDisplay', integer, [ptr])
    handler_type = C.CFUNCTYPE(integer, ptr, ptr)
    handler = handler_type(lambda display, event: 0)
    bind(x, 'XSetErrorHandler', ptr, [handler_type])(handler)
    bind(s, 'SDL_Init', integer, [C.c_uint])
    bind(s, 'SDL_GetError', C.c_char_p, [])
    bind(s, 'SDL_CreateWindow', ptr, [C.c_char_p, integer, integer, integer, integer, C.c_uint])
    bind(s, 'SDL_CreateRenderer', ptr, [ptr, integer, C.c_uint])
    bind(s, 'SDL_GetRendererInfo', integer, [ptr,C.POINTER(RendererInfo)])
    bind(s, 'SDL_GetRendererOutputSize', integer, [ptr, C.POINTER(integer), C.POINTER(integer)])
    bind(s, 'SDL_GetNumVideoDisplays', integer, [])
    bind(s, 'SDL_ShowCursor', integer, [integer])
    bind(s, 'SDL_CreateTexture', ptr, [ptr, C.c_uint, integer, integer, integer])
    bind(s, 'SDL_SetTextureBlendMode', integer, [ptr, integer])
    bind(s, 'SDL_UpdateTexture', integer, [ptr, ptr, ptr, integer])
    bind(s, 'SDL_RenderClear', integer, [ptr])
    bind(s, 'SDL_SetRenderDrawColor', integer, [ptr, C.c_uint8, C.c_uint8, C.c_uint8, C.c_uint8])
    bind(s, 'SDL_RenderCopy', integer, [ptr, ptr, ptr, ptr])
    bind(s, 'SDL_RenderPresent', None, [ptr])
    bind(s, 'SDL_RenderFillRect', integer, [ptr,ptr])
    bind(s, 'SDL_PollEvent', integer, [ptr])
    bind(s, 'SDL_DestroyTexture', None, [ptr])
    bind(s, 'SDL_DestroyRenderer', None, [ptr])
    bind(s, 'SDL_DestroyWindow', None, [ptr])
    bind(s, 'SDL_Quit', None, [])
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('Cannot connect to Xwayland')
    window = renderer = texture = blank_window = blank_renderer = None
    texture_renderer = None
    world_upper = world_lower = None
    world_size = None
    world_frames = WorldFrames()
    world_active = False
    indexed_display = None
    frontend = None
    touch = None
    stick = None
    running = True

    def stop(*args):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # X11 uses the private headless compositor; SDL uses the firmware's
        # existing Wayland session that owns the physical panels.
        if os.environ.get('D2_PRESENT_RUNTIME_DIR'):
            os.environ['XDG_RUNTIME_DIR'] = os.environ['D2_PRESENT_RUNTIME_DIR']
        if os.environ.get('D2_PRESENT_WAYLAND_DISPLAY'):
            os.environ['WAYLAND_DISPLAY'] = os.environ['D2_PRESENT_WAYLAND_DISPLAY']
        if s.SDL_Init(0x20) != 0:
            raise RuntimeError(s.SDL_GetError().decode())
        s.SDL_ShowCursor(0)
        physical_width = int(os.environ.get('D2_PHYSICAL_WIDTH', '1024'))
        physical_height = int(os.environ.get('D2_PHYSICAL_HEIGHT', '768'))
        display_index = int(os.environ.get('D2_SDL_DISPLAY_INDEX', '0'))
        display_count = s.SDL_GetNumVideoDisplays()
        if display_index >= display_count:
            raise RuntimeError(f'Requested panel {display_index}; SDL exposes {display_count} displays')
        if display_count > 1:
            blank_index = 0 if display_index != 0 else 1
            blank_pos = 0x2FFF0000 | blank_index
            blank_window = s.SDL_CreateWindow(b'Diablo II lower panel', blank_pos, blank_pos,
                                             1024, 768, 1 | 4)
            lower_flags = 1 if os.environ.get('D2_LOWER_SOFTWARE') == '1' else 2
            blank_renderer = s.SDL_CreateRenderer(blank_window, -1, lower_flags) if blank_window else None
            if not blank_renderer and blank_window and lower_flags != 1:
                blank_renderer = s.SDL_CreateRenderer(blank_window, -1, 1)
            if not blank_renderer:
                raise RuntimeError('Cannot clear lower panel: ' + s.SDL_GetError().decode())
            s.SDL_SetRenderDrawColor(blank_renderer, 0, 0, 0, 255)
            s.SDL_RenderClear(blank_renderer)
            s.SDL_RenderPresent(blank_renderer)
        position = 0x2FFF0000 | display_index
        window = s.SDL_CreateWindow(b'Diablo II', position, position,
                                    physical_width, physical_height, 1 | 4)
        renderer = s.SDL_CreateRenderer(window, -1, 2 | 4) if window else None
        if not renderer and window:
            renderer = s.SDL_CreateRenderer(window, -1, 1)
        if not renderer:
            raise RuntimeError(s.SDL_GetError().decode())
        for label,value in [('upper',renderer),('lower',blank_renderer)]:
            if value:
                info=RendererInfo()
                if s.SDL_GetRendererInfo(value,C.byref(info))==0:
                    print(f'DISPLAY: {label} driver={info.name.decode()} flags={info.flags}',flush=True)
        # The firmware exposes two separate fullscreen Wayland outputs.
        destination = Rect(0, 0, 1024, 768)
        s.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255)
        actual_width, actual_height = integer(), integer()
        s.SDL_GetRendererOutputSize(renderer, C.byref(actual_width), C.byref(actual_height))
        print(f'DISPLAY: panel={display_index} renderer={actual_width.value}x{actual_height.value} lower-UI', flush=True)
        touch = LowerTouch(x, display, weston / 'lib_aarch64')
        if os.environ.get('D2_FRONTEND_ASSETS') and blank_renderer:
            from frontend_panels import FrontendPanels
            frontend = FrontendPanels(s,renderer,blank_renderer,Rect,os.environ['D2_FRONTEND_ASSETS'],os.environ.get('D2_FRONTEND_REPORT'))
        stick = LeftStick(touch)
        touch.prepare()
        if os.environ.get('D2_INPUT_READY'):
            Path(os.environ['D2_INPUT_READY']).write_text(str(os.getpid()))
        root = x.XDefaultRootWindow(display)
        def find_window(parent_window, depth=0):
            children = C.POINTER(ulong)()
            root_out, parent_out, count = ulong(), ulong(), C.c_uint()
            best = None
            if depth > 8:
                return None
            if x.XQueryTree(display, parent_window, C.byref(root_out), C.byref(parent_out), C.byref(children), C.byref(count)):
                try:
                    for i in range(count.value):
                        attrs = Attributes()
                        child = children[i]
                        if not x.XGetWindowAttributes(display, child, C.byref(attrs)) or attrs.map_state != 2:
                            continue
                        candidate = find_window(child, depth + 1)
                        if candidate is None and 100 <= attrs.width <= 2048 and 60 <= attrs.height <= 2048:
                            candidate = (depth, attrs.width * attrs.height, child, attrs.width, attrs.height)
                        if candidate and (best is None or candidate[:2] >= best[:2]):
                            best = candidate
                finally:
                    if children:
                        x.XFree(children)
            return best

        size = None
        target = None
        event = C.create_string_buffer(64)
        frames = 0
        started = time.monotonic()
        profile = bool(os.environ.get('D2_RENDER_PROFILE'))
        samples = []
        profile_saved = started
        while running:
            frame_start = time.monotonic()
            native_size = None
            if target:
                attrs = Attributes()
                if x.XGetWindowAttributes(display, target, C.byref(attrs)):
                    native_size = attrs.width, attrs.height
                    ox, oy, child = integer(), integer(), ulong()
                    if x.XTranslateCoordinates(display, target, root, 0, 0, C.byref(ox), C.byref(oy), C.byref(child)):
                        touch.origin = ox.value, oy.value
            touch.poll()
            while s.SDL_PollEvent(event):
                if C.c_uint.from_buffer(event).value == 0x100:
                    running = False
            read_started = time.monotonic()
            world = world_frames.read(direct=True)
            read_done = time.monotonic()
            if native_size and native_size != (640, 480):
                world = None  # scene exit: show the new menu immediately
            stick.poll(world is not None, world_frames.movement_blocked,world_frames.movement_rearm)
            if world is WorldFrames.busy:
                world_frames.wait()
                continue
            if world and blank_renderer:
                width, height, upper_pixels, lower_pixels = world
                touch.cursor_item = world_frames.cursor_item
                touch.logical_size = width, height
                indexed=world_frames.version==4
                if world_size != (width, height, indexed):
                    if indexed_display: indexed_display.close();indexed_display=None
                    if world_upper: s.SDL_DestroyTexture(world_upper)
                    if world_lower: s.SDL_DestroyTexture(world_lower)
                    world_upper = s.SDL_CreateTexture(renderer, 0x16362004, 1, 1 if indexed else width, 1 if indexed else height)
                    world_lower = s.SDL_CreateTexture(blank_renderer, 0x16362004, 1, 1 if indexed else width, 1 if indexed else height)
                    if not world_upper or not world_lower:
                        raise RuntimeError(s.SDL_GetError().decode())
                    world_size = width, height, indexed
                    if indexed:
                        from indexed_display import IndexedDisplay
                        indexed_display=IndexedDisplay([renderer,blank_renderer],[world_upper,world_lower],width,height)
                        if not indexed_display.gpu:
                            s.SDL_DestroyTexture(world_upper);s.SDL_DestroyTexture(world_lower)
                            world_upper=s.SDL_CreateTexture(renderer,0x16362004,1,width,height)
                            world_lower=s.SDL_CreateTexture(blank_renderer,0x16362004,1,width,height)
                    print(f'DISPLAY: continuous-world {width}x{height} per panel', flush=True)
                if indexed:
                    indexed_display.upload(upper_pixels,lower_pixels,world_frames.palette)
                    if not indexed_display.gpu:
                        s.SDL_UpdateTexture(world_upper,None,indexed_display.buffers[0],width*4)
                        s.SDL_UpdateTexture(world_lower,None,indexed_display.buffers[1],width*4)
                else:
                    s.SDL_UpdateTexture(world_upper, None, upper_pixels, width * 4)
                    s.SDL_UpdateTexture(world_lower, None, lower_pixels, width * 4)
                uploaded=time.monotonic()
                if not world_frames.is_current():
                    # Both textures will be overwritten together next time.
                    # Per-bank generation stamps detect actual overwrites,
                    # even before the next metadata publication. A newer
                    # publication in the other bank does not invalidate this
                    # coherent pair. Never present a partly updated pair.
                    continue
                s.SDL_RenderClear(renderer)
                s.SDL_RenderClear(blank_renderer)
                if indexed and indexed_display.gpu:
                    indexed_display.draw(0);indexed_display.draw(1)
                    indexed_display.validate(upper_pixels,lower_pixels,world_frames.palette,world_frames.sequence)
                else:
                    s.SDL_RenderCopy(renderer, world_upper, None, C.byref(destination))
                    s.SDL_RenderCopy(blank_renderer, world_lower, None, C.byref(destination))
                if stick.ui:stick.ui.draw(s,blank_renderer,Rect)
                if world_frames.selected_target and not world_frames.movement_blocked:
                    # Prototype target feedback lives entirely on the lower HUD.
                    # The modern UI will replace this drawing, retaining its state.
                    for color,rect in (((185,157,92),Rect(392,12,240,24)),
                                       ((20,20,20),Rect(394,14,236,20)),
                                       ((165,30,25),Rect(396,16,round(232*world_frames.target_health/1000),16)),
                                       ((230,218,178),Rect(370,22,16,2)),
                                       ((230,218,178),Rect(377,15,2,16))):
                        s.SDL_SetRenderDrawColor(blank_renderer,*color,255)
                        s.SDL_RenderFillRect(blank_renderer,C.byref(rect))
                    s.SDL_SetRenderDrawColor(blank_renderer,0,0,0,255)
                copied=time.monotonic()
                # A direct GLES draw leaves no queued SDL command to activate
                # its renderer during RenderPresent. Swap each own context.
                if indexed and indexed_display.gpu:indexed_display.activate(0)
                s.SDL_RenderPresent(renderer)
                upper_presented=time.monotonic()
                if indexed and indexed_display.gpu:indexed_display.activate(1)
                s.SDL_RenderPresent(blank_renderer)
                if profile:
                    now=time.monotonic()
                    samples.append([world_frames.sequence,now,(read_done-read_started)*1000,(now-read_done)*1000,(copied-read_done)*1000,(now-copied)*1000,(uploaded-read_done)*1000,(copied-uploaded)*1000,(upper_presented-copied)*1000,(now-upper_presented)*1000])
                    if now-profile_saved>=5:
                        import json
                        Path('/tmp/d2-classic-display-profile.json').write_text(json.dumps(samples[-1500:]))
                        samples=samples[-1500:];profile_saved=now
                world_active = True
                frames += 1
                world_frames.wait()
                continue
            if world_active:
                s.SDL_RenderClear(blank_renderer)
                s.SDL_RenderPresent(blank_renderer)
                world_active = False
            candidate = find_window(root)
            selected = candidate[2:] if candidate else None
            if selected:
                xid, width, height = selected
                pic = x.XGetImage(display, xid, 0, 0, width, height, ulong(-1), 2)
                if pic:
                    try:
                        img = pic.contents
                        if img.bits_per_pixel != 32 or img.red_mask != 0xFF0000 or img.byte_order != 0:
                            raise RuntimeError('Unsupported X11 pixel format')
                        ui_renderer = native_frame_renderer((width, height), renderer, blank_renderer)
                        if size != (width, height) or texture_renderer != ui_renderer:
                            if texture:
                                s.SDL_DestroyTexture(texture)
                            texture = s.SDL_CreateTexture(ui_renderer, 0x16362004, 1, width, height)
                            if not texture:
                                raise RuntimeError(s.SDL_GetError().decode())
                            size = (width, height)
                            texture_renderer = ui_renderer
                            panel = 'upper' if ui_renderer == renderer else 'lower'
                            print(f'DISPLAY: native={width}x{height} panel={panel}', flush=True)
                            touch.gesture.cancel() if touch.gesture else None
                            touch.logical_size = size
                        if target != xid:
                            print(f'DISPLAY: window={xid} size={width}x{height}', flush=True)
                            target = xid
                        if s.SDL_UpdateTexture(texture, None, img.data, img.bytes_per_line) != 0:
                            raise RuntimeError(s.SDL_GetError().decode())
                        if frontend:
                            frontend.classify(size,img.data,img.bytes_per_line,stick.ui.last_gui if stick.ui else None)
                        present_native_frame(s, renderer, blank_renderer, texture,
                                             destination, size, stick.ui, frontend)
                        frames += 1
                    finally:
                        x.XDestroyImage(pic)
            time.sleep(max(0, 1 / 30 - (time.monotonic() - frame_start)))
        print(f'DISPLAY: frames={frames} seconds={time.monotonic() - started:.1f}', flush=True)
    finally:
        if frontend: frontend.close()
        if indexed_display:indexed_display.close()
        if stick: stick.close()
        if touch: touch.close()
        if world_upper: s.SDL_DestroyTexture(world_upper)
        if world_lower: s.SDL_DestroyTexture(world_lower)
        if texture:
            s.SDL_DestroyTexture(texture)
        if renderer:
            s.SDL_DestroyRenderer(renderer)
        if window:
            s.SDL_DestroyWindow(window)
        if blank_renderer:
            s.SDL_DestroyRenderer(blank_renderer)
        if blank_window:
            s.SDL_DestroyWindow(blank_window)
        s.SDL_Quit()
        x.XCloseDisplay(display)


if __name__ == '__main__':
    main()
