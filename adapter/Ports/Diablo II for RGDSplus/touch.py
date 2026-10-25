"""Lower-panel evdev touch, batched packet parsing and mouse gestures."""
import ctypes as C
from collections import deque
import json
import os
from pathlib import Path
import struct
import time


class TouchDiagnostics:
    def __init__(self, marker='/tmp/d2-touch-trace.enabled', output='/tmp/d2-touch-diagnostics.json'):
        self.enabled = Path(marker).is_file()
        self.output = Path(output)
        self.events = deque(maxlen=2048)
        self.last_saved = 0
        self.last_poll = None

    def record(self, kind, **values):
        if self.enabled:
            self.events.append(dict(kind=kind,mono=time.monotonic_ns(),wall=time.time_ns(),**values))

    def poll(self):
        if self.enabled:
            now = time.monotonic_ns()
            if self.last_poll is not None:
                self.record('poll',gapMs=(now-self.last_poll)/1_000_000)
            self.last_poll = now

    def packet(self, data, reports):
        if self.enabled:
            raw = [list(TouchPackets.event.unpack_from(data,offset))
                   for offset in range(0,len(data)-TouchPackets.event.size+1,TouchPackets.event.size)]
            self.record('evdev',raw=raw,reports=reports)

    def flush(self, force=False):
        if not self.enabled:
            return
        now = time.monotonic_ns()
        if not force and now-self.last_saved<1_000_000_000:
            return
        try:
            temporary = self.output.with_suffix('.next')
            temporary.write_text(json.dumps({'pid':os.getpid(),'stamp':now,'events':list(self.events)}))
            temporary.replace(self.output)
            self.last_saved = now
        except OSError:
            self.enabled = False


# The lower panel reports short ghost contacts on a few fixed rows. Treat a
# short contact on one of these rows as hardware noise, not game input.
NOISE_ROWS = ((466, 2), (730, 12))


def on_noise_row(row):
    return row is not None and any(abs(row-center) <= tolerance for center, tolerance in NOISE_ROWS)


def panel_point(x, y, logical_size, ranges=(0, 1024, 0, 768)):
    width, height = logical_size
    xmin, xmax, ymin, ymax = ranges
    px = round((x - xmin) * (width - 1) / max(1, xmax - xmin))
    py = round((y - ymin) * (height - 1) / max(1, ymax - ymin))
    return max(0, min(width - 1, px)), max(0, min(height - 1, py))


class TouchPackets:
    """Track complete Type-B contacts and cancel ambiguous gestures."""
    event = struct.Struct('<qqHHi')

    def __init__(self, x=0, y=0, clock=time.monotonic, bounds=None):
        self.buffer = bytearray()
        self.slot = 0
        self.mt = False
        self.slots = {0: {53:x, 54:y, 57:-1}}
        self.active = None
        self.blocked = False
        self.clear_since = None
        self.clock = clock
        self.bounds = bounds
        self.reason = None
        self.needs_resync = False
        self.legacy_down = False
        self.x, self.y = x, y
        self.last = (False, x, y)
        self.dropped = False
        self.contact_started = {}
        self.scanline_noise_history = deque(maxlen=16)
        self.ignored_contacts = set()

    def cancel(self, reason):
        self.active = None
        self.blocked = True
        self.clear_since = None
        self.reason = reason
        state = (None, self.x, self.y)
        changed = state != self.last
        self.last = state
        return [state] if changed else []

    def resync(self, slots, selected):
        self.buffer.clear()
        self.slots = {slot:dict(values) for slot,values in slots.items()}
        self.slot = selected
        self.mt = True
        self.active = None
        self.contact_started.clear()
        self.ignored_contacts = {(slot, values.get(57)) for slot, values in slots.items() if values.get(57,-1)>=0}
        self.blocked = any(values.get(57,-1)>=0 for values in slots.values())
        self.clear_since = None
        self.dropped = self.needs_resync = False
        self.last = (None if self.blocked else False, self.x, self.y)

    def commit(self, stamp=None):
        now = self.clock()
        if stamp is not None and stamp > 0:
            now = stamp
        if not self.mt:
            state = (self.legacy_down, self.x, self.y)
        else:
            current = {(slot, values.get(57)) for slot, values in self.slots.items() if values.get(57,-1)>=0}
            self.ignored_contacts.intersection_update(current)
            live = [(slot,values) for slot,values in self.slots.items()
                    if values.get(57,-1)>=0 and (slot,values.get(57)) not in self.ignored_contacts]
            stamp_now = stamp if stamp is not None else now
            # Recurring short contacts on the measured scanline are classified
            # per tracking ID before multi-touch cancellation can poison the
            # RC10 gesture state. A released contact is removed immediately.
            for slot,values in live:
                key=(slot,values.get(57))
                started,row=self.contact_started.get(key,(None,None))
                age=stamp_now-started if started is not None else None
                history=[t for t in self.scanline_noise_history if 0<=stamp_now-t<=.75]
                if (row is not None and on_noise_row(row) and age is not None and
                        0<=age<=.05 and len(history)>=2):
                    self.ignored_contacts.add(key)
            current={(slot,values.get(57)) for slot,values in self.slots.items() if values.get(57,-1)>=0}
            self.ignored_contacts.intersection_update(current)
            live=[(slot,values) for slot,values in live if (slot,values.get(57)) not in self.ignored_contacts]
            live = [(slot,values) for slot,values in live
                    if not self._is_suppressed((slot,values.get(57)), values, stamp_now)]
            if len(live)>1:
                known_rows=[values.get(54) for _,values in live if values.get(54) is not None]
                scanline_cluster=(known_rows and max(known_rows)-min(known_rows)<=2 and
                                  any(on_noise_row(row) for row in known_rows))
                if scanline_cluster:
                    # Leave this transient multi-slot scanline frame out of
                    # the pointer path without latching blocked state.
                    return []
                return self.cancel('multiple-contacts')
            if self.blocked:
                if not live:
                    if self.clear_since is None:
                        self.clear_since = now
                    return []
                if self.clear_since is None or now-self.clear_since<.25:
                    self.clear_since = None
                    return []
                self.blocked = False
                self.clear_since = None
            if not live:
                self.active = None
                state = (False, self.x, self.y)
            else:
                slot, values = live[0]
                contact = (slot,values[57])
                if self.active is not None and self.active!=contact:
                    return self.cancel('contact-replaced')
                if 53 not in values or 54 not in values:
                    return self.cancel('missing-coordinates')
                column, row = values[53], values[54]
                if self.bounds:
                    xmin,xmax,ymin,ymax = self.bounds
                    if not xmin<=column<=xmax or not ymin<=row<=ymax:
                        return self.cancel('invalid-coordinates')
                self.active = contact
                self.x,self.y = column,row
                state = (True,column,row)
        if state == self.last:
            return []
        self.last = state
        return [state]

    def feed(self, data):
        self.buffer.extend(data)
        reports = []
        while len(self.buffer) >= self.event.size:
            seconds, micros, kind, code, value = self.event.unpack_from(self.buffer)
            del self.buffer[:self.event.size]
            if kind == 0 and code == 3:
                self.legacy_down = False
                reports.extend(self.cancel('syn-dropped'))
                self.dropped = True
                self.needs_resync = True
                continue
            if self.needs_resync:
                continue
            if self.dropped:
                if kind == 0 and code == 0:
                    self.dropped = False
                continue
            if kind == 3:
                if code == 47:
                    self.slot = value
                elif code in (53, 54, 57):
                    self.mt = True
                    if 0<=self.slot<32:
                        stamp=seconds+micros/1_000_000
                        if code==57 and value>=0:
                            key=(self.slot,value)
                            if key not in self.contact_started:
                                self.contact_started[key]=(stamp,self.slots.get(self.slot,{}).get(54))
                        elif code==57 and value==-1:
                            old_id=self.slots.get(self.slot,{}).get(57,-1)
                            started,row=self.contact_started.pop((self.slot,old_id),(None,None))
                            if (started is not None and row is not None and on_noise_row(row) and
                                    0<=stamp-started<=.05):
                                self.scanline_noise_history.append(stamp)
                        elif code==54:
                            tracking=self.slots.get(self.slot,{}).get(57,-1)
                            key=(self.slot,tracking)
                            if tracking>=0 and key in self.contact_started:
                                self.contact_started[key]=(self.contact_started[key][0],value)
                        self.slots.setdefault(self.slot,{})[code] = value
                        tracking=self.slots[self.slot].get(57,-1)
                        if tracking>=0:
                            key=(self.slot,tracking)
                            if self._is_suppressed(key,self.slots[self.slot],seconds+micros/1_000_000):
                                # Suppress only this tracking ID. It is removed
                                # from the live set again on the next SYN.
                                self.ignored_contacts.add(key)
                    else:
                        reports.extend(self.cancel('invalid-slot'))
                elif not self.mt:
                    if code == 0: self.x = value
                    elif code == 1: self.y = value
            elif kind == 1 and code == 330:
                self.legacy_down = bool(value)
            elif kind == 0 and code == 0:
                reports.extend(self.commit(seconds+micros/1_000_000))
        return reports

    def _is_suppressed(self, contact, values, stamp):
        started,row=self.contact_started.get(contact,(None,None))
        if (values.get(54) is None or not on_noise_row(values.get(54)) or
                started is None or not 0<=stamp-started<=.05):
            return False
        recent=[t for t in self.scanline_noise_history if 0<=stamp-t<=.75]
        return len(recent)>=4


class GhostFilteredTouchPackets:
    """Admit only finger-like contacts and drop short/noisy ghost contacts.

    A new contact must report both a fresh X and a fresh Y, its touch-major
    width must be in the human-finger range, and it must remain down for a
    short confirmation interval. A stationary tap is emitted on release so
    it is not lost while waiting for a second SYN.
    """
    event = struct.Struct('<qqHHi')
    minimum_seconds = .045
    width_minimum = 25
    width_maximum = 100

    def __init__(self, x=0, y=0, clock=time.monotonic, bounds=None, require_width=True):
        self.buffer = bytearray()
        self.slot = 0
        self.mt = False
        self.slots = {0: {53: x, 54: y, 57: -1}}
        self.active = None
        self.blocked = False
        self.clear_since = None
        self.clock = clock
        self.bounds = bounds
        self.require_width = require_width
        self.reason = None
        self.needs_resync = False
        self.legacy_down = False
        self.x, self.y = x, y
        self.last = (False, x, y)
        self.dropped = False
        self.contact_meta = {}
        self.ignored_contacts = set()

    def cancel(self, reason):
        self.active = None
        self.blocked = True
        self.clear_since = None
        self.reason = reason
        self.contact_meta.clear()
        state = (None, self.x, self.y)
        changed = state != self.last
        self.last = state
        return [state] if changed else []

    def resync(self, slots, selected):
        self.buffer.clear()
        self.slots = {slot: dict(values) for slot, values in slots.items()}
        self.slot = selected
        self.mt = True
        self.active = None
        self.contact_meta.clear()
        self.ignored_contacts = {(slot, values.get(57)) for slot, values in slots.items()
                                 if values.get(57, -1) >= 0}
        self.blocked = bool(self.ignored_contacts)
        self.clear_since = None
        self.dropped = self.needs_resync = False
        self.last = (None if self.blocked else False, self.x, self.y)

    def _meta(self, key, stamp):
        if key not in self.contact_meta:
            self.contact_meta[key] = {
                'start': stamp, 'x': None, 'y': None, 'width': None,
                'fresh_x': False, 'fresh_y': False, 'forwarded': False,
            }
        return self.contact_meta[key]

    def _valid(self, key, values):
        meta = self.contact_meta.get(key)
        if meta is None or not (meta['fresh_x'] and meta['fresh_y']):
            return False
        width = meta['width']
        if width is None:
            return not self.require_width
        return self.width_minimum <= width <= self.width_maximum

    def _release(self, now):
        key = self.active
        if key is None:
            return []
        meta = self.contact_meta.pop(key, None)
        self.ignored_contacts.discard(key)
        self.active = None
        if meta is None:
            return []
        x = meta['x'] if meta['x'] is not None else self.x
        y = meta['y'] if meta['y'] is not None else self.y
        if meta['forwarded']:
            state = (False, x, y)
            self.last = state
            return [state]
        if (meta['width'] is not None and meta['fresh_x'] and meta['fresh_y']
                and now - meta['start'] >= self.minimum_seconds):
            self.last = (False, x, y)
            return [(True, x, y), (False, x, y)]
        self.last = (False, x, y)
        return []

    def commit(self, stamp=None):
        now = stamp if stamp is not None and stamp > 0 else self.clock()
        if not self.mt:
            state = (self.legacy_down, self.x, self.y)
        else:
            current = {(slot, values.get(57)) for slot, values in self.slots.items()
                       if values.get(57, -1) >= 0}
            self.ignored_contacts.intersection_update(current)
            live = [(slot, values) for slot, values in self.slots.items()
                    if values.get(57, -1) >= 0
                    and (slot, values.get(57)) not in self.ignored_contacts]
            for slot, values in live:
                if 53 not in values or 54 not in values:
                    return self.cancel('missing-coordinates')
            for slot, values in live:
                key = (slot, values.get(57))
                if not self._valid(key, values):
                    self.ignored_contacts.add(key)
            live = [(slot, values) for slot, values in live
                    if (slot, values.get(57)) not in self.ignored_contacts]
            if len(live) > 1:
                return self.cancel('multiple-contacts')
            if self.blocked:
                if not live:
                    if self.clear_since is None:
                        self.clear_since = now
                    return []
                if self.clear_since is None or now - self.clear_since < .25:
                    self.clear_since = None
                    return []
                self.blocked = False
                self.clear_since = None
            if not live:
                reports = self._release(now)
                if reports:
                    return reports
                if self.last[0] is None:
                    return []
                state = (False, self.x, self.y)
            else:
                slot, values = live[0]
                key = (slot, values.get(57))
                if self.active is not None and self.active != key:
                    return self.cancel('contact-replaced')
                if 53 not in values or 54 not in values:
                    return self.cancel('missing-coordinates')
                column, row = values[53], values[54]
                if self.bounds:
                    xmin, xmax, ymin, ymax = self.bounds
                    if not xmin <= column <= xmax or not ymin <= row <= ymax:
                        return self.cancel('invalid-coordinates')
                meta = self.contact_meta.get(key)
                if meta is None:
                    meta = self._meta(key, now)
                self.active = key
                self.x, self.y = column, row
                if meta['forwarded']:
                    state = (True, column, row)
                elif meta['width'] is None:
                    # Legacy/synthetic contacts without width are trusted.
                    meta['forwarded'] = True
                    state = (True, column, row)
                elif now - meta['start'] < self.minimum_seconds:
                    # Hold the down until the contact proves it is not a
                    # short controller glitch. A release after the threshold
                    # is converted to a tap in _release().
                    self.last = (False, column, row)
                    return []
                else:
                    meta['forwarded'] = True
                    state = (True, column, row)
        if state == self.last:
            return []
        self.last = state
        return [state]

    def feed(self, data):
        self.buffer.extend(data)
        reports = []
        while len(self.buffer) >= self.event.size:
            seconds, micros, kind, code, value = self.event.unpack_from(self.buffer)
            del self.buffer[:self.event.size]
            stamp = seconds + micros / 1_000_000
            if kind == 0 and code == 3:
                self.legacy_down = False
                reports.extend(self.cancel('syn-dropped'))
                self.dropped = True
                self.needs_resync = True
                continue
            if self.needs_resync:
                continue
            if self.dropped:
                if kind == 0 and code == 0:
                    self.dropped = False
                continue
            if kind == 3:
                if code == 47:
                    self.slot = value
                elif code in (53, 54, 48, 50, 57):
                    self.mt = True
                    if not 0 <= self.slot < 32:
                        reports.extend(self.cancel('invalid-slot'))
                        continue
                    slot_values = self.slots.setdefault(self.slot, {})
                    if code == 57:
                        slot_values[57] = value
                        if value >= 0:
                            self._meta((self.slot, value), stamp)
                    else:
                        slot_values[code] = value
                        tracking = slot_values.get(57, -1)
                        if tracking >= 0:
                            meta = self.contact_meta.get((self.slot, tracking))
                            if meta is not None:
                                if code == 53:
                                    meta['x'] = value
                                    meta['fresh_x'] = True
                                elif code == 54:
                                    meta['y'] = value
                                    meta['fresh_y'] = True
                                elif code in (48, 50):
                                    meta['width'] = value
                elif not self.mt:
                    if code == 0:
                        self.x = value
                    elif code == 1:
                        self.y = value
            elif kind == 1 and code == 330:
                self.legacy_down = bool(value)
            elif kind == 0 and code == 0:
                reports.extend(self.commit(stamp))
        return reports


TouchPackets = GhostFilteredTouchPackets


class MouseGesture:
    """Tap sends one click; holding 450 ms starts a held left-button drag."""
    def __init__(self, move, button, clock=time.monotonic, can_drop=lambda: False, click_drag=lambda: False):
        self.move, self.button, self.clock = move, button, clock
        self.active = self.held = False
        self.started = 0
        self.origin = self.position = (0, 0)
        self.release_at = None
        self.drop_at = None
        self.can_drop = can_drop
        self.click_drag=click_drag
        self.pickup_release_at=None
        self.inventory_drag=False

    def update(self, down, point):
        now = self.clock()
        if down and not self.active:
            self.cancel()
            self.active = True
            self.started = now
            self.origin = self.position = point
            self.move(*point)
        elif down:
            self.position = point
            if self.pickup_release_at is None: self.move(*point)
        elif self.active:
            self.active = False
            self.position = point
            if self.held:
                if self.pickup_release_at is None:
                    self.move(*point)
                    self.button(False)
                self.held = False
                if point != self.origin and (self.can_drop() or self.inventory_drag):
                    # Classic inventory uses a second click to place the
                    # cursor item. Keep world long-holds as a single press.
                    self.drop_at = now + (.16 if self.inventory_drag else .08)
            else:
                self.move(*point)
                self.button(True)
                self.release_at = now + .08

    def tick(self):
        now = self.clock()
        if self.active and not self.held and now - self.started >= .45:
            self.move(*self.origin)
            self.button(True)
            self.held = True
            self.inventory_drag=self.click_drag()
            if self.inventory_drag: self.pickup_release_at=now+.08
            else: self.move(*self.position)
        if self.pickup_release_at is not None and now>=self.pickup_release_at:
            self.button(False)
            self.pickup_release_at=None
            self.move(*self.position)
        if self.release_at is not None and now >= self.release_at:
            self.button(False)
            self.release_at = None
        if self.drop_at is not None and now >= self.drop_at:
            self.drop_at = None
            if self.can_drop():
                self.button(True)
                self.release_at = now + .08

    def cancel(self):
        if self.held or self.release_at is not None or self.pickup_release_at is not None: self.button(False)
        self.active = self.held = False
        self.release_at = None
        self.drop_at = None
        self.pickup_release_at=None
        self.inventory_drag=False


def coalesce_reports(reports, active=False):
    cancelled = next((report for report in reversed(reports) if report[0] is None),None)
    if cancelled is not None:
        return [cancelled]
    result = []
    pending = None
    for down, column, row in reports:
        report = (down, column, row)
        if down and active:
            pending = report
            continue
        if pending is not None:
            result.append(pending)
            pending = None
        result.append(report)
        active = bool(down)
    if pending is not None:
        result.append(pending)
    return result


class LowerTouch:
    def __init__(self, xlib, display, library_root):
        self.diagnostics = TouchDiagnostics()
        self.fd = None
        self.xtest = None
        self.active = False
        self.library_root = Path(library_root)
        self.packets = TouchPackets()
        self.ranges = (0, 1024, 0, 768)
        self.logical_size = (800, 600)
        self.origin = (0, 0)
        self.xlib, self.display = xlib, display
        self.gesture = None
        self.cursor_item = False
        self.full_ui=None
        self.overlay_touch=None
        self.ui_consumed=False
        self.key_queue=[]; self.key_pending=None; self.key_due=0
        self.qa_stamp=0; self.qa_down=False
        self.waiting_for_release = False
        self.physical_activity = False

    def activate(self):
        """Enable game input inside the private game display session."""
        if self.active:
            return
        try:
            import fcntl
            xtest = C.CDLL(str(self.library_root / 'libXtst.so.6'))
            xtest.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
            xtest.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
            xtest.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
            self.xlib.XFlush.argtypes = [C.c_void_p]
            self.xtest = xtest
            self.active = True
            for name in Path('/sys/class/input').glob('event*/device/name'):
                if name.read_text().strip().lower() != 'gt9xx-0': continue
                path = '/dev/input/' + name.parents[1].name
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                try:
                    limits = []
                    positions = []
                    for preferred, fallback in ((53, 0), (54, 1)):
                        for axis in (preferred, fallback):
                            value = bytearray(24)
                            try:
                                fcntl.ioctl(fd, 0x80184540 + axis, value, True)
                                current, low, high, _, _, _ = struct.unpack('<6i', value)
                                if high > low:
                                    limits.extend((low, high))
                                    if axis in (53, 54):
                                        slots = bytearray(struct.pack('<2i', axis, 0))
                                        try:
                                            fcntl.ioctl(fd, 0x8008450a, slots, True)
                                            current = struct.unpack_from('<i', slots, 4)[0]
                                        except OSError: pass
                                    positions.append(current)
                                    break
                            except OSError: pass
                        else: raise RuntimeError('Touch axis capability unavailable')
                    # Grab only this touch device for the lifetime of the game
                    # session. This is per-file-descriptor isolation, not a
                    # firmware/system touch-mode change; without it the
                    # desktop and the private game X session both receive the
                    # same finger and the desktop pointer jumps.
                    fcntl.ioctl(fd, 0x40044590, struct.pack('i', 1))
                    self.fd, self.ranges = fd, tuple(limits)
                    # The kernel omits unchanged ABS values. Seed the first
                    # contact with slot zero's position instead of (0, 0).
                    self.packets = TouchPackets(*positions,bounds=self.ranges)
                    self.resync()
                    self.gesture = MouseGesture(self.move, self.button, can_drop=lambda: self.cursor_item,
                                                click_drag=lambda: bool(self.full_ui and self.full_ui.page=='inventory'))
                    print(f'TOUCH: grabbed {path} ranges={self.ranges} lower-panel', flush=True)
                    break
                except Exception:
                    os.close(fd)
                    self.fd = None
                    raise
            if self.fd is None:
                print('TOUCH: gt9xx-0 unavailable; controller XTest remains available', flush=True)
        except (OSError, RuntimeError) as error:
            self.active = False
            self.xtest = None
            print(f'TOUCH: game bridge unavailable {error}', flush=True)

    def move(self, px, py):
        if not self.xtest:
            return
        self.diagnostics.record('move',point=[px,py],logicalSize=list(self.logical_size))
        if self.full_ui: px,py=self.full_ui.to_native(px,py)
        self.xtest.XTestFakeMotionEvent(self.display, 0, px + self.origin[0], py + self.origin[1], 0)
        self.xlib.XFlush(self.display)

    def button(self, down):
        if not self.xtest:
            return
        self.diagnostics.record('button',down=bool(down),point=list(self.gesture.position))
        self.xtest.XTestFakeButtonEvent(self.display, 1, int(down), 0)
        self.xlib.XFlush(self.display)
        print(f'TOUCH: left={int(down)} at={self.gesture.position} logical={self.logical_size}', flush=True)

    def resync(self):
        import fcntl
        data = bytearray(24)
        fcntl.ioctl(self.fd, 0x80184540+47, data, True)
        selected, minimum, maximum, unused, flat, resolution = struct.unpack('<6i',data)
        count = maximum+1
        if minimum!=0 or not 1<=count<=32:
            raise RuntimeError('Invalid touch slot capacity')
        slots = {slot:{} for slot in range(count)}
        for axis in (53,54,57):
            values = bytearray(struct.pack('<'+str(count+1)+'i',axis,*([0]*count)))
            fcntl.ioctl(self.fd,0x8000450a|(len(values)<<16),values,True)
            for slot,value in enumerate(struct.unpack('<'+str(count+1)+'i',values)[1:]):
                slots[slot][axis] = value
        self.packets.resync(slots,selected)
        self.diagnostics.record('resync',slot=selected,slots=slots)

    def read_reports(self):
        reports = []
        self.physical_activity = False
        for attempt in range(8):
            try:
                data = os.read(self.fd, TouchPackets.event.size * 4096)
            except BlockingIOError:
                break
            if not data:
                break
            self.physical_activity = True
            received = self.packets.feed(data)
            self.diagnostics.packet(data, received)
            reports.extend(received)
        if self.packets.needs_resync:
            self.resync()
        return reports

    def prepare(self):
        if self.fd is None and not getattr(self, 'active', False):
            print('TOUCH: waiting for native game window', flush=True)
            return
        if self.fd is None:
            print('TOUCH: game touch unavailable; controller remains active', flush=True)
            return
        self.gesture.cancel()
        # Observe before the native game starts. Never forward boot-time noise.
        deadline = time.monotonic()+1.0
        while time.monotonic()<deadline:
            self.read_reports()
            time.sleep(.01)
        self.resync()
        self.waiting_for_release = False
        print('TOUCH: ready; startup input discarded', flush=True)

    def key_sequence(self,keys):
        self.key_queue.extend(keys)

    def poll_keys(self):
        if not self.xtest:
            return
        now=time.monotonic()
        if self.key_pending is not None and now>=self.key_due:
            self.xtest.XTestFakeKeyEvent(self.display,self.key_pending,0,0); self.xlib.XFlush(self.display)
            self.key_pending=None; self.key_due=now+.08
        if self.key_pending is None and self.key_queue and now>=self.key_due:
            name=self.key_queue.pop(0)
            code=self.xlib.XKeysymToKeycode(self.display,self.xlib.XStringToKeysym(name.encode()))
            self.xtest.XTestFakeKeyEvent(self.display,code,1,0); self.xlib.XFlush(self.display)
            self.key_pending=code; self.key_due=now+.08

    def poll(self):
        if self.fd is None or ('active' in self.__dict__ and not self.active): return
        self.diagnostics.poll()
        self.poll_keys()
        if os.environ.get('D2_QA_INPUT')=='1': self.poll_qa()
        try:
            reports = self.read_reports()
            if self.physical_activity and os.environ.get('D2_QA_INPUT')=='1' and os.environ.get('D2_QA_TOUCH_GUARD'):
                Path(os.environ['D2_QA_TOUCH_GUARD']).write_text(str(time.monotonic_ns()))
                return
            selected = coalesce_reports(reports, self.gesture.active)
            self.diagnostics.record('batch',received=len(reports),selected=len(selected))
            for down, column, row in selected:
                self.report(down,column,row)
            self.gesture.tick()
            self.diagnostics.flush()
        except OSError as error:
            print(f'TOUCH: input lost {error}', flush=True)
            self.close()

    def report(self,down,x,y):
        if not self.xtest or not self.gesture:
            return
        if self.waiting_for_release:
            if not down:
                self.waiting_for_release = False
            return
        physical=panel_point(x,y,(1024,768),self.ranges)
        if self.overlay_touch and self.overlay_touch(down,physical,self.logical_size):
            self.gesture.cancel();self.ui_consumed=False
            return
        point=panel_point(x,y,self.logical_size,self.ranges)
        self._gesture_report(down, point)

    def _gesture_report(self, down, point):
        if down is None:
            self.gesture.cancel(); self.ui_consumed=False
        elif self.ui_consumed:
            if not down: self.ui_consumed=False
        elif down and not self.gesture.active and self.full_ui and self.full_ui.action(*point):
            page=self.full_ui.action(*point); current=self.full_ui.page
            if page=='close': self.key_sequence(['Escape'])
            elif page!=current:
                key={'inventory':'i','character':'c','skills':'t'}
                self.key_sequence([key[current],key[page]])
            self.ui_consumed=True
        else: self.gesture.update(down,point)

    def poll_qa(self):
        # QA feeds the same post-evdev report path; no firmware input is sent.
        try:
            owner=Path('/tmp/diablo2-classic-controller-qa.pid').read_text().strip()
            if not Path('/proc/'+owner).exists(): raise ValueError('QA ended')
            request=json.loads(Path('/tmp/d2-classic-touch-qa.json').read_text())
            if abs(time.monotonic_ns()-request['stamp'])>200_000_000: raise ValueError('Stale QA touch')
            if request['stamp']!=self.qa_stamp:
                self.qa_stamp=request['stamp']
                received=time.monotonic_ns()
                if 'evdev' in request:
                    events=request['evdev']
                    if len(events)>16384:
                        raise ValueError('QA packet too large')
                    raw=b''.join(TouchPackets.event.pack(0,0,*event) for event in events)
                    reports=coalesce_reports(self.packets.feed(raw),self.gesture.active)
                    self.diagnostics.record('qa-evdev',events=len(events),reports=reports)
                else:
                    reports=request.get('reports',[[request.get('down',False),request.get('x',0),request.get('y',0)]])
                for down,x,y in reports:
                    self.report(None if down is None else bool(down),int(x),int(y))
                    self.qa_down=bool(down)
                Path('/tmp/d2-classic-touch-ack.json').write_text(json.dumps({'stamp':self.qa_stamp,'received':received,'completed':time.monotonic_ns(),'reports':len(reports)}))
        except (OSError,ValueError,KeyError):
            if self.qa_down: self.report(None,0,0); self.qa_down=False

    def close(self):
        if self.gesture: self.gesture.cancel()
        self.diagnostics.flush(force=True)
        if self.key_pending is not None and self.xtest:
            self.xtest.XTestFakeKeyEvent(self.display,self.key_pending,0,0); self.xlib.XFlush(self.display)
            self.key_pending=None
        self.key_queue.clear()
        if self.fd is not None:
            os.close(self.fd)  # releases EVIOCGRAB
            self.fd = None
        self.active = False
        self.xtest = None
