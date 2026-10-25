"""RGDSplus left-stick actions, independent of UI pixel positions."""
import ctypes as C
import math
import mmap
import os
from pathlib import Path
import struct
import time
import json
from combat import CombatInput
from ui_controller import UIControllerBridge

EVENT=struct.Struct('<qqHHi')
MAGIC=0x44325349
R3_CODE=316  # PortMaster rightstick:b12; JS button map b12 -> evdev 316.
X_CODE=306

def radial(x,y,deadzone=.18):
    length=math.hypot(x,y)
    if length<=deadzone: return 0.,0.
    scale=(min(length,1.)-deadzone)/(1.-deadzone)/length
    return x*scale,y*scale

class StickState:
    def __init__(self):
        self.axes={2:0.,3:0.,4:0.,5:0.}
        self.combat=CombatInput()
        self.direct=True
        self.rearm=True
        self.buffer=b''
        self.r3=False
        self.toggle=False
        self.dropped=False
        self.ui_buttons={};self.ui_edges=[];self.hat={16:0,17:0};self.toggle_allowed=True

    def button_event(self,code,value):
        if value not in (0,1):return
        down=bool(value)
        if self.ui_buttons.get(code,False)!=down:self.ui_edges.append((code,down))
        self.ui_buttons[code]=down

    def feed(self,data,ranges):
        self.buffer+=data
        commits=[]
        while len(self.buffer)>=EVENT.size:
            _,_,kind,code,value=EVENT.unpack_from(self.buffer)
            self.buffer=self.buffer[EVENT.size:]
            if kind==1:self.button_event(code,value)
            if kind==0 and code==3:
                self.dropped=True; self.rearm=True
                self.combat.cancel()
            elif self.dropped:
                if kind==0 and code==0:
                    self.dropped=False
                    commits.append(None)  # caller resynchronizes kernel axes
            elif kind==3 and code in self.hat:
                self.hat[code]=max(-1,min(1,value))
            elif kind==3 and code in self.axes:
                low,high=ranges[code]
                center=(low+high)/2
                self.axes[code]=max(-1.,min(1.,(value-center)/((high-low)/2)))
            elif kind==1 and code==R3_CODE:
                pressed=bool(value)
                if pressed and not self.r3 and self.toggle_allowed: self.toggle=True
                self.r3=pressed
            elif kind==1:
                self.combat.feed(code,value)
            elif kind==0 and code==0:
                if self.toggle:
                    self.direct=not self.direct; self.rearm=True; self.toggle=False
                commits.append(radial(self.axes[2],self.axes[3]))
        return commits

    def command(self,world,blocked,touch):
        x,y=radial(self.axes[2],self.axes[3])
        length=math.hypot(x,y)
        if not world or blocked or touch or not self.direct: self.rearm=True
        if length==0:
            self.rearm=False
            return 0,0,0
        if self.rearm: return 0,0,0
        flags=1 | (2 if length>=.65 else 0)
        return flags,round(x/length*32767),round(y/length*32767)

class LeftStick:
    def __init__(self,touch):
        self.fd=None; self.mapping=None; self.sequence=0; self.store=None
        self.state=StickState(); self.ranges={}; self.touch=touch
        self.last=time.monotonic(); self.last_touch=0.
        self.world=False; self.blocked=True
        self.ui_buttons=set(); self.qa_keys=set(); self.qa_active=False
        self.ui=None
        if os.environ.get('D2_DIRECT_MOVE','0')!='1': return
        try:
            import fcntl
            for name in Path('/sys/class/input').glob('event*/device/name'):
                if name.read_text().strip()!='ANBERNIC-rk3568-keys': continue
                self.fd=os.open('/dev/input/'+name.parents[1].name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
                for axis in (2,3,4,5):
                    info=bytearray(24)
                    fcntl.ioctl(self.fd,0x80184540+axis,info,True)
                    value,low,high,_,_,_=struct.unpack('<6i',info)
                    if high<=low: raise RuntimeError('Invalid left-stick axis range')
                    self.ranges[axis]=(low,high)
                    self.state.axes[axis]=(value-(low+high)/2)/((high-low)/2)
                break
            if self.fd is None: raise RuntimeError('RGDSplus controller not found')
            path=os.environ['D2_STICK_FRAME']
            fd=os.open(path,os.O_CREAT|os.O_TRUNC|os.O_RDWR,0o600)
            try:
                os.ftruncate(fd,64)
                self.mapping=mmap.mmap(fd,64)
            finally: os.close(fd)
            # ARM requires release ordering for the shared command seqlock.
            atomic=C.CDLL('/lib/libatomic.so.1')
            self.fence=atomic.atomic_thread_fence
            self.fence.argtypes=[C.c_int]; self.fence.restype=None
            self.store=getattr(atomic,'__atomic_store_4')
            self.store.argtypes=[C.c_void_p,C.c_uint32,C.c_int]; self.store.restype=None
            self.sequence_address=C.addressof(C.c_char.from_buffer(self.mapping))+8
            self.load=getattr(atomic,'__atomic_load_4')
            self.load.argtypes=[C.c_void_p,C.c_int]; self.load.restype=C.c_uint32
            self.ack_address=self.sequence_address+40
            x=self.touch.xlib
            x.XStringToKeysym.argtypes=[C.c_char_p]; x.XStringToKeysym.restype=C.c_ulong
            x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong]; x.XKeysymToKeycode.restype=C.c_uint
            self.touch.xtest.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
            x=self.touch.xlib
            x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),
                                     C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]
            x.XQueryPointer.restype=C.c_int
            self.publish(0,0,0)
            self.ui=UIControllerBridge(touch)
            print(f'STICK: axes=2,3 ranges={self.ranges} direct-move; R3 toggles cursor',flush=True)
        except (OSError,RuntimeError,KeyError,AttributeError) as error:
            print(f'STICK: disabled {error}; right-stick cursor/touch remain available',flush=True)
            self.close()

    def publish(self,flags,x,y,aim_x=0,aim_y=0,held=0,event=0):
        if self.mapping is None or self.store is None: return
        self.sequence+=2
        self.store(self.sequence_address,self.sequence-1,5)
        struct.pack_into('<2I',self.mapping,0,MAGIC,2)
        struct.pack_into('<IQii',self.mapping,12,flags,time.monotonic_ns(),x,y)
        struct.pack_into('<iiII',self.mapping,32,aim_x,aim_y,held,event)
        self.fence(5)
        self.store(self.sequence_address,self.sequence,5)

    def cursor(self,x,y,elapsed):
        if not self.touch.gesture: return
        root,child=C.c_ulong(),C.c_ulong()
        rx,ry,wx,wy=C.c_int(),C.c_int(),C.c_int(),C.c_int()
        mask=C.c_uint()
        lib=self.touch.xlib
        if not lib.XQueryPointer(self.touch.display,lib.XDefaultRootWindow(self.touch.display),C.byref(root),C.byref(child),
                                 C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask)): return
        width,height=self.touch.logical_size
        ox,oy=self.touch.origin
        cx,cy=rx.value-ox,ry.value-oy
        if self.touch.full_ui: cx,cy=self.touch.full_ui.from_native(cx,cy)
        px=max(0,min(width-1,round(cx+x*360*elapsed)))
        py=max(0,min(height-1,round(cy+y*360*elapsed)))
        self.touch.move(px,py)

    def click_cursor(self,down):
        t=self.touch
        if not t.xtest: return
        t.xtest.XTestFakeButtonEvent(t.display,1,int(down),0)
        t.xlib.XFlush(t.display)

    def ui_route(self,edges):
        for code,down in edges:
            if code==305 and self.touch.full_ui and self.touch.full_ui.page:
                if down: self.touch.key_sequence(['Escape'])
                continue
            if code in (304,305):
                self.touch.xtest.XTestFakeButtonEvent(self.touch.display,1 if code==304 else 3,int(down),0)
                if down: self.ui_buttons.add(code)
                else: self.ui_buttons.discard(code)
            elif code==307:
                key=self.touch.xlib.XKeysymToKeycode(self.touch.display,self.touch.xlib.XStringToKeysym(b'i'))
                self.touch.xtest.XTestFakeKeyEvent(self.touch.display,key,int(down),0)
                if down: self.ui_buttons.add(code)
                else: self.ui_buttons.discard(code)
        self.touch.xlib.XFlush(self.touch.display)

    def qa_input(self):
        # Only the muted, bounded supervisor enables this private injection.
        # Firmware's menu never receives these QA buttons.
        if os.environ.get('D2_QA_INPUT')!='1': return
        request=None
        try:
            owner=Path('/tmp/diablo2-classic-controller-qa.pid').read_text().strip()
            if not Path('/proc/'+owner).exists(): raise ValueError('QA owner exited')
            request=json.loads(Path('/tmp/d2-classic-qa.json').read_text())
            if abs(time.monotonic_ns()-request['stamp'])>200_000_000: request=None
        except (OSError,ValueError,KeyError): pass
        if request is None and not self.qa_active: return
        for axis,value in zip((2,3,4,5),(request or {}).get('axes',[0,0,0,0])):
            self.state.axes[axis]=max(-1.,min(1.,float(value)))
        keys=set((request or {}).get('keys',[]))
        for code in self.qa_keys|keys:
            if code==R3_CODE and code in keys and code not in self.qa_keys and self.state.toggle_allowed:
                self.state.direct=not self.state.direct;self.state.rearm=True
            self.state.button_event(code,int(code in keys))
            self.state.combat.feed(code,int(code in keys))
        for axis,value in zip((16,17),(request or {}).get('hat',[0,0])):self.state.hat[axis]=max(-1,min(1,int(value)))
        self.qa_keys=keys; self.qa_active=request is not None

    def poll(self,world,blocked=False,require_neutral=False):
        if self.fd is None: return
        now=time.monotonic(); elapsed=min(.05,now-self.last); self.last=now
        self.state.toggle_allowed=bool(self.ui and self.ui.logic.page=='world')
        try:
            while True:
                try: data=os.read(self.fd,EVENT.size*64)
                except BlockingIOError: break
                if not data: raise OSError('Controller disconnected')
                old=self.state.direct
                for commit in self.state.feed(data,self.ranges):
                    if commit is None:
                        import fcntl
                        self.ui_route([(code,False) for code in tuple(self.ui_buttons)])
                        keys=bytearray(96)
                        fcntl.ioctl(self.fd,0x80604518,keys,True)
                        self.state.combat.buttons={code:bool(keys[code//8]&(1<<(code%8))) for code in (304,305,307,308,309,315)}
                        self.state.combat.cancel()
                        self.state.ui_edges.clear()
                        if self.ui:self.ui.output.cancel()
                        self.state.ui_buttons={code:bool(keys[code//8]&(1<<(code%8))) for code in (304,305,306,307,308,309,311,312,313,314,315,316)}
                        for axis in (2,3,4,5):
                            info=bytearray(24)
                            fcntl.ioctl(self.fd,0x80184540+axis,info,True)
                            value,low,high,_,_,_=struct.unpack('<6i',info)
                            self.state.axes[axis]=(value-(low+high)/2)/((high-low)/2)
                if old!=self.state.direct:
                    print('STICK: mode='+('direct' if self.state.direct else 'cursor')+'; neutral required',flush=True)
            gesture=self.touch.gesture
            busy=bool(gesture and (gesture.active or gesture.held or gesture.release_at is not None or gesture.drop_at is not None))
            if busy: self.last_touch=now
            busy=busy or now-self.last_touch<.3
            self.qa_input()
            # Minimal world interaction: X sends one left click at the
            # current game cursor. Dialogs/panels keep their normal X action.
            if world and self.ui and self.ui.logic.page=='world':
                interact=[edge for edge in self.state.ui_edges if edge[0]==X_CODE]
                self.state.ui_edges=[edge for edge in self.state.ui_edges if edge[0]!=X_CODE]
                self.state.combat.edges=[edge for edge in self.state.combat.edges if edge[0]!=X_CODE]
                for code,down in interact:
                    self.click_cursor(down)
            if self.ui:self.ui.poll(self.state,world,busy)
            if world and require_neutral: self.state.rearm=True
            allowed=bool(world and not blocked and not busy and self.state.direct and (not self.ui or not self.ui.logic.active))
            held,event,edges=self.state.combat.command(allowed,self.load(self.ack_address,2))
            # UI-generated presses always receive release on a context change.
            if not self.ui:
                if allowed and self.ui_buttons: self.ui_route([(code,False) for code in tuple(self.ui_buttons)])
                if not busy: self.ui_route(edges)
                else:self.ui_route([(code,False) for code in tuple(self.ui_buttons)])
            ax,ay=radial(self.state.axes[4],self.state.axes[5])
            self.publish(*self.state.command(world,blocked,busy),round(ax*32767),round(ay*32767),held,event)
            if (not self.ui or not self.ui.logic.active) and (not world or blocked or not self.state.direct) and not busy:
                self.cursor(*radial(self.state.axes[2],self.state.axes[3]),elapsed)
        except OSError as error:
            print(f'STICK: input lost {error}',flush=True)
            self.close()

    def close(self):
        if self.ui:self.ui.close()
        if self.ui_buttons: self.ui_route([(code,False) for code in tuple(self.ui_buttons)])
        self.publish(0,0,0)
        if self.fd is not None: os.close(self.fd); self.fd=None
        if self.mapping is not None: self.mapping.close(); self.mapping=None
