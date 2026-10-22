"""Fresh native UI observation and owned X11 output for the UI navigator."""
from collections import deque
import ctypes as C
import json,os,struct,time
from pathlib import Path
from ui_navigation import ControllerUI
from touch_keyboard import TouchKeyboard

class NativeGUIState:
    def __init__(self,path='/tmp/d2-classic-gui.bin'):self.path=Path(path)
    def read(self):
        try:
            for _ in range(3):
                data=self.path.read_bytes()
                if len(data)!=8192:return None
                w=struct.unpack('<2048I',data)
                if w[0]!=0x44324755 or w[1]!=1:return None
                if w[2]&1 or struct.unpack_from('<I',self.path.read_bytes(),8)[0]!=w[2]:continue
                stamp=w[5]|w[6]<<32
                if not 0<=time.monotonic_ns()-stamp<800_000_000:return None
                controls=[]
                for i in range(min(w[3],64)):
                    r=w[32+i*24:56+i*24]
                    title='' if r[1]>=100 else struct.pack('<16I',*r[8:24]).decode('utf-16le',errors='replace').split('\0',1)[0]
                    control=dict(id=r[0],type=r[1],flags=r[2],rect=list(r[3:7]),actionable=bool(r[7]),title=title)
                    if r[1]>=100:control.update(value=r[8],choices=r[9],label_cell=r[10],slider_left=r[11])
                    if r[1]==111:control['skill']=r[8]
                    controls.append(control)
                return dict(controls=controls,complete=not w[4],menu=w[7],rows=w[8],kind=w[9],stamp=stamp,sequence=w[2])
        except (OSError,struct.error):pass
        return None

class NativeUIState:
    def __init__(self,path='/tmp/d2-classic-ui.bin'):self.path=Path(path)
    def read(self):
        try:
            for _ in range(3):
                data=self.path.read_bytes()
                if len(data)!=16384:return None
                w=struct.unpack('<4096I',data)
                if w[0]!=0x44325549 or w[1]!=1:return None
                after=struct.unpack_from('<I',self.path.read_bytes(),8)[0]
                if w[2]&1 or after!=w[2]:continue
                stamp=w[20]|w[21]<<32
                if not 0<=time.monotonic_ns()-stamp<800_000_000:return None
                mask=w[22]|w[26]<<32;items=[]
                for i in range(min(w[4],400)):
                    u=w[32+i*9:41+i*9]
                    if u[0]==4:items.append(dict(id=u[1],class_=u[2],mode=u[3],x=u[4],y=u[5],page=u[8]&255,body=(u[8]>>8)&255,owned=bool(u[8]&0x10000)))
                for u in items:u['class']=u.pop('class_')
                controls=[]
                for i in range(min(w[8],10)):
                    r=w[3712+i*8:3720+i*8];controls.append(dict(index=r[0],rect=list(r[1:5]),flags=r[5],callback=r[6],parameter=r[7]))
                return dict(sequence=w[2],stamp=stamp,complete=not w[6],flags={i for i in range(64) if mask&(1<<i)},blocked=w[3],
                            cursor_type=w[24],cursor_id=w[25],class_=w[31],**{'class':min(w[31],6)},
                            stat_points=w[27],skill_points=w[28],gold=w[29],stash_gold=w[30],items=items,controls=controls,menu_selected=w[9])
        except (OSError,struct.error):pass
        return None

class UIOutput:
    def __init__(self,touch):
        self.touch=touch;self.queue=deque();self.until=0.;self.mouse=set();self.keys=set()
    def emit(self,op,*args):
        if op=='cancel':self.cancel();return
        if op=='move':
            if not self.queue:self.motion(args[0])
            return
        if op=='click':
            point,button,mods=args
            for key in mods:self.queue.append(('kd',key,.02))
            self.queue.extend([('move',point,.06),('md',button,.09),('mu',button,.1)])
            for key in reversed(mods):self.queue.append(('ku',key,.03))
        elif op in ('key','keys'):
            for key in [args[0]] if op=='key' else args[0]:self.queue.extend([('kd',key,.09),('ku',key,.09)])
        elif op=='hold_key':self.queue.append(('kd' if args[1] else 'ku',args[0],0))
        elif op=='hold_button':self.queue.append(('md' if args[1] else 'mu',args[0],0))
    def motion(self,point):
        t=self.touch;x,y=map(round,point)
        t.xtest.XTestFakeMotionEvent(t.display,0,x+t.origin[0],y+t.origin[1],0);t.xlib.XFlush(t.display)
    def key(self,name,down):
        t=self.touch;code=t.xlib.XKeysymToKeycode(t.display,t.xlib.XStringToKeysym(name.encode()))
        if not code:return
        t.xtest.XTestFakeKeyEvent(t.display,code,int(down),0);t.xlib.XFlush(t.display)
        (self.keys.add if down else self.keys.discard)(name)
    def button(self,button,down):
        t=self.touch;t.xtest.XTestFakeButtonEvent(t.display,button,int(down),0);t.xlib.XFlush(t.display)
        (self.mouse.add if down else self.mouse.discard)(button)
    def tick(self):
        if self.queue and time.monotonic()>=self.until:
            op,arg,delay=self.queue.popleft()
            if op=='move':self.motion(arg)
            elif op in ('kd','ku'):self.key(arg,op=='kd')
            else:self.button(arg,op=='md')
            self.until=time.monotonic()+delay
    def cancel(self):
        self.queue.clear();self.until=0
        for button in tuple(self.mouse):self.button(button,False)
        for key in tuple(self.keys):self.key(key,False)

class UIControllerBridge:
    def __init__(self,touch):
        self.touch=touch;self.reader=NativeUIState();self.gui_reader=NativeGUIState();self.output=UIOutput(touch)
        profile=json.loads((Path(__file__).parent/'controller-layout.json').read_text(encoding='utf-8'))
        self.logic=ControllerUI(profile,self.output.emit,time.monotonic);self.last_hat=(0,0);self.last_report=0;self.touch_busy=False
        self.keyboard=TouchKeyboard(self.logic)
        self.touch.overlay_touch=self.keyboard.touch
        self.last_gui=None
        self.last=time.monotonic();self.font=None;self.cursor_neutral=True;self.cursor_context=None
    def poll(self,state,world,busy):
        if self.logic.cursor_mode != (not state.direct):
            self.output.cancel();self.logic.suppressed.update(k for k,v in state.ui_buttons.items() if v)
        self.logic.cursor_mode=not state.direct
        native=self.reader.read();gui=self.gui_reader.read()
        if gui:self.last_gui=gui
        elif not world and self.last_gui and 0<=time.monotonic_ns()-self.last_gui['stamp']<400_000_000:
            gui=self.last_gui
        semantic=native
        if gui:
            semantic=dict(native) if native else dict(flags=set(),blocked=False,cursor_type=6,cursor_id=0,items=[],complete=True)
            semantic['gui']=gui
        self.logic.sync(semantic,world)
        self.keyboard.sync(gui,world)
        cursor_context=(self.logic.page,self.logic.gui_signature)
        if cursor_context!=self.cursor_context:self.cursor_neutral=True
        self.cursor_context=cursor_context
        if busy:
            if not self.touch_busy:self.output.cancel();self.logic.holds.clear()
            self.logic.neutral=True
            self.cursor_neutral=True
            self.logic.buttons.update(state.ui_buttons)
            self.logic.suppressed.update(k for k,v in state.ui_buttons.items() if v)
            state.ui_edges.clear();self.touch_busy=True;return
        self.touch_busy=False
        now=time.monotonic();elapsed=min(.05,now-self.last);self.last=now
        rx,ry=state.axes[4],state.axes[5]
        if max(abs(rx),abs(ry))<=.2:self.cursor_neutral=False
        if self.logic.active and not self.cursor_neutral and max(abs(rx),abs(ry))>.2 and not self.logic.text_keyboard:
            t=self.touch;root,child=C.c_ulong(),C.c_ulong();x,y,wx,wy=C.c_int(),C.c_int(),C.c_int(),C.c_int();mask=C.c_uint()
            if t.xlib.XQueryPointer(t.display,t.xlib.XDefaultRootWindow(t.display),C.byref(root),C.byref(child),C.byref(x),C.byref(y),C.byref(wx),C.byref(wy),C.byref(mask)):
                width,height=t.logical_size
                point=(max(0,min(width-1,round(x.value-t.origin[0]+rx*360*elapsed))),max(0,min(height-1,round(y.value-t.origin[1]+ry*360*elapsed))))
                self.logic.pointer_override=point;self.logic.focus=next((n for n in self.logic.nodes if n.contains(point)),None)
                self.logic.last_input=now;self.output.emit('move',point)
        for code,down in state.ui_edges:self.logic.button(code,down)
        state.ui_edges.clear()
        hx,hy=state.hat[16],state.hat[17]
        if not self.logic.active:
            if (hx,hy)!=self.last_hat and (hx or hy):self.output.emit('key','2' if hx>0 else '4' if hx<0 else '3' if hy>0 else '1')
        else:self.logic.axes(state.axes[2],state.axes[3],hx,hy)
        self.last_hat=(hx,hy)
        self.logic.tick();self.output.tick()
        if os.environ.get('D2_QA_INPUT')=='1' and time.monotonic()-self.last_report>.08:
            snapshot=self.logic.snapshot();snapshot['stamp']=time.monotonic_ns()
            snapshot['native_sequence']=native['sequence'] if native else None
            snapshot['gui']=gui
            snapshot['keyboard_visible']=self.logic.text_keyboard
            snapshot['keyboard_touch_events']=self.keyboard.events
            snapshot['keyboard_output_pending']=len(self.output.queue)
            target=Path('/tmp/d2-classic-controller-state.json');temporary=target.with_suffix('.next')
            temporary.write_text(json.dumps(snapshot));temporary.replace(target)
            self.last_report=time.monotonic()
    def draw(self,s,renderer,rect_type):
        if not self.logic.active or self.logic.page=='loading':return
        n=self.logic.focus
        if n and self.logic.active and time.monotonic()-self.logic.last_input<15:
            x,y,w,h=n.rect;lw,lh=self.touch.logical_size
            r=rect_type(round(x*1024/lw),round(y*768/lh),round(w*1024/lw),round(h*768/lh))
            s.SDL_SetRenderDrawColor(renderer,225,190,90,255)
            # Four thin edges avoid adding a new SDL binding.
            for e in [rect_type(r.x,r.y,r.w,2),rect_type(r.x,r.y+r.h-2,r.w,2),rect_type(r.x,r.y,2,r.h),rect_type(r.x+r.w-2,r.y,2,r.h)]:s.SDL_RenderFillRect(renderer,C.byref(e))
            s.SDL_SetRenderDrawColor(renderer,0,0,0,255)
        def fill(x,y,w,h,color):
            s.SDL_SetRenderDrawColor(renderer,*color,255);r=rect_type(x,y,w,h);s.SDL_RenderFillRect(renderer,C.byref(r))
        def text(value,x,y,scale=1):
            if not self.font:
                raw=bytearray((Path(__file__).parent/'controller-font.bin').read_bytes())
                for offset in range(0,len(raw),4):
                    if raw[offset:offset+3]==b'\x0f\x0f\x0f':raw[offset+3]=0
                buf=C.create_string_buffer(bytes(raw))
                self.font=s.SDL_CreateTexture(renderer,0x16362004,1,192,120)
                if not self.font or s.SDL_UpdateTexture(self.font,None,buf,192*4):return
                s.SDL_SetTextureBlendMode.argtypes=[C.c_void_p,C.c_int]
                s.SDL_SetTextureBlendMode(self.font,1)
                # Separate lower renderer owns this font for the session.
            for i,ch in enumerate(value):
                index=max(0,min(94,ord(ch)-32));a=rect_type(index%16*12,index//16*20,12,20)
                b=rect_type(round(x+i*12*scale),round(y),round(12*scale),round(20*scale));s.SDL_RenderCopy(renderer,self.font,C.byref(a),C.byref(b))
        if self.logic.text_keyboard:
            fill(*self.keyboard.panel,(15,15,15))
            text('NAME / TEXT',40,174)
            text('Tap keys, then DONE',40,210)
            for label,box in (('CLOSE',self.keyboard.close_rect),('ABC' if self.logic.uppercase else 'abc',self.keyboard.case_rect)):
                fill(*box,(65,57,43));text(label,box[0]+14,box[1]+10)
            for i,key in enumerate(self.logic.keyboard):
                x,y,w,h=self.keyboard.key_rect(i)
                fill(x,y,w,h,(100,78,35) if i==self.logic.text_index else (50,45,37))
                label=key if len(key)>1 or self.logic.uppercase else key.lower()
                scale=1.6 if len(label)==1 else 1.
                text(label,x+(w-len(label)*12*scale)/2,y+(h-20*scale)/2,scale)
        elif self.keyboard.edit:
            box=self.keyboard.open_rect;fill(*box,(50,45,37));text('KEYBOARD',box[0]+20,box[1]+12)
        if self.logic.message:text(self.logic.message[:65],12,720,.85)
        s.SDL_SetRenderDrawColor(renderer,0,0,0,255)
    def close(self):
        self.touch.overlay_touch=None
        self.output.cancel()
