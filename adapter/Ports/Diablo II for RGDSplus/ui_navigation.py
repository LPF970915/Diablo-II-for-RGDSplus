"""Controller UI semantics in native coordinates; artwork/layout is replaceable."""
from dataclasses import dataclass,field
import math

# RGDSplus cap legends, deliberately independent of SDL's Xbox labels.
A,B,X,Y,L1,R1,SELECT,START,L2,R2,L3,R3=305,304,306,307,308,309,312,311,314,315,313,316
PAGES=['character','inventory','skills','quests']
PAGE_KEYS=dict(character='c',inventory='i',skills='t',quests='q',mercenary='o')
PRIORITY=[(11,'settings'),(9,'pause'),(23,'dialog'),(24,'messages'),(14,'service'),(26,'cube'),(25,'stash'),(12,'shop'),(37,'scroll'),(8,'npc'),
          (20,'waypoint'),(36,'mercenary'),(4,'skills'),(2,'character'),
          (15,'quests'),(22,'party'),(33,'help'),(5,'text'),(3,'quickskills'),(1,'inventory')]

@dataclass
class Node:
    id:str
    rect:list
    group:str='controls'
    action:str='click'
    data:dict=field(default_factory=dict)
    @property
    def point(self): return (round(self.rect[0]+self.rect[2]/2),round(self.rect[1]+self.rect[3]/2))
    def contains(self,p): return self.rect[0]<=p[0]<self.rect[0]+self.rect[2] and self.rect[1]<=p[1]<self.rect[1]+self.rect[3]

def context(state,world):
    if state is None: return 'loading' if world else 'frontend'
    flags=state['flags']
    if 9 in flags and state.get('gui',{}).get('kind')==2:return 'settings'
    for flag,name in PRIORITY:
        if flag in flags:return name
    if state.get('blocked') and state.get('cursor_type')!=4:return 'dialog'
    return 'world' if world else 'frontend'

def nearest(nodes,current,dx,dy):
    if not nodes:return None
    if current not in nodes:return nodes[0]
    x,y=current.point; candidates=[]
    for node in nodes:
        if node is current:continue
        nx,ny=node.point; forward=(nx-x)*dx+(ny-y)*dy
        if forward<=1:continue
        lateral=abs((nx-x)*dy-(ny-y)*dx)
        candidates.append((forward+lateral*3+lateral*lateral/max(forward,1),node.id,node))
    return min(candidates,key=lambda x:x[:2])[2] if candidates else current

def directional_nodes(nodes,current,page):
    if page not in ('stash','cube','shop','mercenary') or not current:return nodes
    other='merc' if page=='mercenary' else page
    def side(n):return other if n.group==other or n.data.get('container')==page else 'inventory'
    return [n for n in nodes if side(n)==side(current)]

def metadata(profile,unit):
    i=unit['class'];return profile['items'][i] if 0<=i<len(profile['items']) else None

def free_cell(profile,grid,units,item):
    spec=profile['grids'][grid]; info=metadata(profile,item)
    if info is None:return None
    occupied=set()
    for unit in units:
        if unit['mode']!=0 or not unit.get('owned') or unit['page']!=spec['page'] or unit['id']==item['id']:continue
        shape=metadata(profile,unit)
        if shape is None:return None
        for y in range(unit['y'],unit['y']+shape['height']):
            for x in range(unit['x'],unit['x']+shape['width']):occupied.add((x,y))
    for y in range(spec['rows']-info['height']+1):
        for x in range(spec['cols']-info['width']+1):
            if not any((px,py) in occupied for py in range(y,y+info['height']) for px in range(x,x+info['width'])):return x,y
    return None

def nodes_for(profile,page,state,tab=0):
    nodes=[]
    def rect(id,bounds,group='controls',action='click',**data):nodes.append(Node(id,list(bounds),group,action,data))
    if page in ('frontend','pause','settings','dialog','quickskills','service') and state.get('gui',{}).get('controls'):
        for c in state['gui']['controls']:
            if not c['flags']&4 or c['type'] not in (1,4,5,6,7,11,12,100,101,102,110,111):continue
            action='edit' if c['type']==1 else 'adjust' if c['type'] in (101,102) else 'click'
            if any(label in c.get('title','').lower() for label in ('delete','删除','刪除')):action='hold_click'
            rect('native:'+str(c['id']),c['rect'],'native',action,kind=c['type'],title=c.get('title',''),
                 value=c.get('value',0),choices=c.get('choices',0),slider_left=c.get('slider_left',0))
        if nodes and page!='service':return sorted(nodes,key=lambda n:(n.rect[1],n.rect[0],n.id))
    def grid(name):
        g=profile['grids'][name]; ox,oy=g['origin'];cw,ch=g['cell']
        for y in range(g['rows']):
            for x in range(g['cols']):rect(f'{name}:{x}:{y}',[ox+x*cw,oy+y*ch,cw,ch],name,'item',x=x,y=y,page=g['page'],foreign=g.get('foreign',False))
    if page in ('inventory','stash','cube','shop','mercenary','service'):
        if page!='mercenary' or 1 in state.get('flags',set()):
            grid('inventory')
            for slot in profile['equipment']:rect(slot['id'],slot['rect'],'equipment','item',body=slot['body'])
            for i in range(4):rect(f'belt:{i}',[344+i*31,441,29,29],'belt','item',belt=i)
            rect('gold',profile['buttons']['gold'],action='gold')
        if page in ('stash','cube','shop'):
            grid(page)
            for id,r in profile['buttons'].items():
                if id.startswith(page+'_'):rect(id,r,action='hold_click' if id in ('cube_transmute','shop_repair_all') else 'gold' if id.startswith('stash_') else 'click',container=page)
        if page=='mercenary':
            for slot in profile['mercenary']:rect(slot['id'],slot['rect'],'merc','item',body=slot['body'])
    elif page=='character':
        for i,r in enumerate(profile['character_points']):rect('stat:'+str(i),r,'stats','stat',stat=i)
    elif page=='skills':
        cls=['ama','sor','nec','pal','bar','dru','ass'][min(6,state.get('class',0))]
        g=profile['skill_grid']
        for skill in profile['skills']:
            if skill['cls']==cls and skill['page']==tab:
                rect('skill:'+str(skill['id']),[g['origin'][0]+skill['col']*g['cell'][0],g['origin'][1]+skill['row']*g['cell'][1],*g['size']],'skills','skill',skill=skill['id'])
    elif page=='waypoint':
        g=profile['waypoint']
        for i in range(g['rows']):rect(f'waypoint:{i}',[g['origin'][0],g['origin'][1]+i*g['row_height'],g['width'],28],'waypoint')
    elif page=='quests':
        g=profile['quest']
        for y in range(g['rows']):
            for x in range(g['cols']):rect(f'quest:{x}:{y}',[g['origin'][0]+x*g['cell'][0],g['origin'][1]+y*g['cell'][1],*g['size']],'quests')
    elif page=='pause':
        for n in profile['pause']:rect(n['id'],n['rect'],action=n.get('action','click'))
    elif page in ('npc','dialog'):
        controls=state.get('controls',[])
        for control in controls:
            if control.get('callback',control['index']>0):rect('menu:'+str(control['index']),control['rect'],'menu')
        # The observed hire list uses this renderer only for its single wide
        # header, with a separate native list control underneath. Restrict the
        # fallback to that header shape; ordinary NPC choices use native rows.
        if page=='npc' and not nodes and len(controls)==1 and controls[0]['index']==0 and controls[0]['rect'][1]<=40 and controls[0]['rect'][2]>=150:
            g=profile['hire_list']
            for i in range(g['rows']):rect('hire:'+str(i),[g['origin'][0],g['origin'][1]+i*g['row_height'],g['width'],g['row_height']],'hire')
            rect('hire_cancel',g['cancel'],'hire')
    return nodes

class ControllerUI:
    """Outputs semantic commands; never executes a game function or writes a stat."""
    def __init__(self,profile,emit,clock):
        self.profile,self.emit,self.clock=profile,emit,clock
        self.page=None;self.state=None;self.focus=None;self.nodes=[];self.remember={};self.buttons={};self.suppressed=set()
        self.holds={};self.tab=0;self.direction=(0,0);self.next_repeat=0.;self.neutral=True
        self.origin=None;self.transaction=None;self.message='';self.last_input=0;self.text_keyboard=False;self.text_index=0;self.switching_until=0;self.pointer_override=None;self.local_modal=None
        self.keyboard=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')+['SPACE','BACK','CLEAR','DONE']
        self.uppercase=False
        self.cursor_mode=False
        self.gui_signature=None

    def sync(self,state,world):
        if self.local_modal=='settings' and state and 9 not in state['flags'] and 11 not in state['flags']:self.local_modal=None
        new=self.local_modal or context(state,world); self.state=state
        gui=(state or {}).get('gui',{})
        signature=(gui.get('menu'),gui.get('rows'),tuple((c['id'],c['type'],tuple(c['rect']),'' if c['type']==1 else c.get('title','')) for c in gui.get('controls',[])))
        if self.page==new and new in ('frontend','pause','settings','dialog') and signature!=self.gui_signature:
            self.emit('cancel')
            self.focus=None;self.remember.pop(new,None);self.pointer_override=None;self.holds.clear()
            self.suppressed.update(k for k,v in self.buttons.items() if v)
        self.gui_signature=signature
        if new!=self.page:
            if self.focus:self.remember[self.page]=self.focus.id
            if self.clock()>=self.switching_until:self.emit('cancel')
            self.suppressed.update(k for k,v in self.buttons.items() if v)
            self.holds.clear();self.transaction=None;self.tab=0;self.neutral=True;self.direction=(0,0)
            self.page=new;self.focus=None;self.message='';self.text_keyboard=False
            self.pointer_override=None
            if new!='gold':self.keyboard=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')+['SPACE','BACK','CLEAR','DONE'];self.text_index=0
            self.rebuild()
        else:self.rebuild(keep=True)
        self.advance_transaction()

    def rebuild(self,keep=False):
        previous=self.focus.id if keep and self.focus else self.remember.get(self.page)
        self.nodes=nodes_for(self.profile,self.page,self.state or {},self.tab)
        if keep and self.pointer_override is not None:
            self.focus=next((n for n in self.nodes if n.contains(self.pointer_override)),None);return
        self.focus=next((n for n in self.nodes if n.id==previous),self.nodes[0] if self.nodes else None)
        if previous is None and self.page=='frontend':
            self.focus=next((n for n in self.nodes if n.data.get('title','').strip().lower() in ('好','確定','确定','ok')),self.focus)

    @property
    def active(self):return self.page!='world'

    def move(self,node):
        if node:
            self.focus=node;self.pointer_override=None;self.last_input=self.clock();self.emit('move',node.point)

    def point(self):return self.pointer_override or (self.focus.point if self.focus else None)

    def item(self):
        if not self.focus or not self.state:return None
        n=self.focus;d=n.data
        for u in self.state['items']:
            if n.group=='belt' and u['owned'] and u['mode']==2 and u['x']==d['belt']:return u
            if n.group=='equipment' and u['owned'] and u['mode']==1 and u['body']==d['body']:return u
            if n.group in self.profile['grids'] and u['mode']==0 and u['page']==d['page'] and u['owned']!=d.get('foreign',False):
                info=metadata(self.profile,u)
                if info and u['x']<=d['x']<u['x']+info['width'] and u['y']<=d['y']<u['y']+info['height']:return u
        return None

    def button(self,code,down):
        was=self.buttons.get(code,False);self.buttons[code]=down
        if not down:self.suppressed.discard(code)
        if code in self.suppressed or down==was:return
        if self.page=='loading':return
        if self.page=='world' and code==L2 and (not down or not self.buttons.get(R2)):
            self.emit('hold_key','Alt_L',down);return
        if self.page=='world' and self.cursor_mode and code in (A,B) and (not down or not self.buttons.get(R2)):
            self.emit('hold_button',1 if code==A else 3,down);return
        if not down:
            self.holds.pop(code,None);return
        self.last_input=self.clock()
        if self.page=='world':self.world_button(code);return
        if self.transaction:return
        if self.page=='quickskills' and self.buttons.get(R2) and code in (B,A,Y,X):
            key={B:'F1',A:'F2',Y:'F3',X:'F4'}[code];self.emit('key',key);self.message='Assigned '+key;return
        if code in (B,START):
            if self.text_keyboard:self.text_keyboard=False
            elif self.state and self.state['cursor_type']==4:
                if self.origin:self.emit('click',self.origin,1,[])
                else:self.message='Place the held item before closing'
            else:
                self.emit('key','Escape')
                if self.local_modal:self.switching_until=self.clock()+.4
                self.local_modal=None
        elif code==SELECT:
            if self.page in PAGES:self.emit('key',PAGE_KEYS[self.page])
            elif self.page=='mercenary':self.emit('key','i')
        elif code in (L1,R1):self.change_page(-1 if code==L1 else 1)
        elif code in (L2,R2):self.change_tab(-1 if code==L2 else 1)
        elif code==R3 and self.page in ('inventory','stash','shop','cube'):self.emit('key','w')
        elif code==A:
            if self.text_keyboard:
                self.keyboard_key(self.keyboard[self.text_index])
            elif self.point():
                if self.focus and self.focus.action=='adjust':
                    if self.focus.data['kind']==101:
                        x,y,w,h=self.focus.rect;self.emit('click',(round(x+w-12),round(y+h/2)),1,[])
                    else:self.message='Left / Right: adjust'
                elif self.focus and self.focus.action in ('stat','skill','hold_click'):self.holds[code]=(self.clock(),self.focus.id)
                else:
                    if (self.item() or self.focus and self.focus.group=='merc') and self.state['cursor_type']!=4:self.origin=self.point()
                    self.emit('click',self.point(),1,[])
                    if self.focus and self.focus.action=='gold':
                        self.local_modal='gold';self.switching_until=self.clock()+.5
                        self.keyboard=list('0123456789')+['BACK','CLEAR','DONE'];self.text_index=0
                    elif self.focus and self.focus.action=='edit':self.text_keyboard=True
                    elif self.focus and self.focus.action=='options' and not (self.state or {}).get('gui'):self.local_modal='settings';self.switching_until=self.clock()+.5
            else:
                self.emit('key','Return')
                if self.page=='gold':self.local_modal=None;self.switching_until=self.clock()+.4
        elif code in (X,Y):
            if self.page in ('frontend','text','dialog','gold','settings'):
                if code==Y:self.text_keyboard=not self.text_keyboard
                else:self.emit('key','space')
            elif self.page in ('npc','party','help','quest_text','quickskills','scroll'):
                if code==X:self.emit('key','Tab')
            elif self.focus:self.holds[code]=(self.clock(),self.focus.id)

    def keyboard_key(self,key):
        if key=='DONE':
            self.text_keyboard=False;self.emit('key','Return')
            if self.local_modal:self.local_modal=None;self.switching_until=self.clock()+.4
        elif key=='CLEAR':self.emit('keys',['End']+['BackSpace']*16)
        elif key=='BACK':self.emit('key','BackSpace')
        elif key=='SPACE':self.emit('key','space')
        else:
            if self.uppercase and key.isalpha():self.emit('hold_key','Shift_L',True)
            self.emit('key',key.lower())
            if self.uppercase and key.isalpha():self.emit('hold_key','Shift_L',False)

    def world_button(self,code):
        if self.buttons.get(R2) and code in (B,A,Y,X,L1,R1):
            if code==R1:
                self.switching_until=self.clock()+.65;self.emit('keys',['o','i'])
            else:self.emit('key',{B:'F1',A:'F2',Y:'F3',X:'F4',L1:'c'}[code])
        elif code==SELECT:self.emit('key','s' if self.buttons.get(R2) else 'i')
        elif self.buttons.get(R2) and code in (L2,L3,START):self.emit('key',{L2:'h',L3:'Return',START:'p'}[code])
        elif code==START:self.emit('key','Escape')
        elif code==X:self.emit('key','Tab')
        elif code==L3:self.emit('key','r')
        elif code==Y and self.cursor_mode:self.emit('key','i')

    def change_page(self,delta):
        if self.page in PAGES and self.state and self.state['cursor_type']==4:return
        if self.page=='npc' and self.focus and self.focus.group=='hire':self.emit('click',self.focus.point,4 if delta<0 else 5,[])
        elif self.page in PAGES:
            other=PAGES[(PAGES.index(self.page)+delta)%len(PAGES)]
            self.switching_until=self.clock()+.65
            self.emit('keys',[PAGE_KEYS[self.page],PAGE_KEYS[other]])
        elif self.page in ('stash','cube','shop','mercenary'):
            other='merc' if self.page=='mercenary' else self.page
            current=other if self.focus and (self.focus.group==other or self.focus.data.get('container')==self.page) else 'inventory'
            target='inventory' if current==other else other
            node=next((n for n in self.nodes if n.group==target),None)
            if node:self.move(node)
            elif self.page=='mercenary' and target=='inventory':self.emit('key','i')
        else:self.emit('key','Page_Up' if delta<0 else 'Page_Down')

    def change_tab(self,delta):
        if self.state and self.state['cursor_type']==4:return
        key='skill_tabs' if self.page=='skills' else 'shop_tabs' if self.page=='shop' else None
        if key:tabs=self.profile[key]
        elif self.page in ('quests','waypoint'):tabs=self.profile['quest' if self.page=='quests' else 'waypoint']['tabs']
        else:return
        self.tab=(self.tab+delta)%len(tabs);r=tabs[self.tab]
        self.emit('click',(round(r[0]+r[2]/2),round(r[1]+r[3]/2)),1,[])
        self.holds.clear();self.rebuild(keep=self.page=='shop')

    def axes(self,x,y,hx,hy):
        if not self.active or self.page=='loading':return
        if hx or hy:x,y=hx,hy
        if max(abs(x),abs(y))<.5:
            self.direction=(0,0);self.neutral=False;return
        if self.neutral or self.transaction:return
        direction=(int(math.copysign(1,x)),0) if abs(x)>abs(y) else (0,int(math.copysign(1,y)))
        now=self.clock()
        if direction!=self.direction or now>=self.next_repeat:
            self.next_repeat=now+(self.profile['repeat_delay'] if direction!=self.direction else self.profile['repeat_interval'])
            self.direction=direction
            if self.text_keyboard:
                self.text_index=(self.text_index+direction[0]+direction[1]*10)%len(self.keyboard)
            elif self.focus and self.focus.action=='adjust' and direction[0]:
                x,y,w,h=self.focus.rect;d=self.focus.data;self.next_repeat=max(self.next_repeat,now+.38)
                if d['kind']==102 and d['choices']>1:
                    value=max(0,min(d['choices']-1,d['value']+direction[0]))
                    self.emit('click',(round(d['slider_left']+12+266*value/(d['choices']-1)),round(y+h/2)),1,[])
                elif 1<d['choices']<=32:
                    count=1 if direction[0]>0 else d['choices']-1
                    for _ in range(count):self.emit('click',(round(x+w-12),round(y+h/2)),1,[])
                    self.next_repeat=max(self.next_repeat,now+count*.3+.1)
            elif self.nodes:self.move(nearest(directional_nodes(self.nodes,self.focus,self.page),self.focus,*direction))
            else:self.emit('key',('Right' if direction[0]>0 else 'Left') if direction[0] else ('Down' if direction[1]>0 else 'Up'))

    def tick(self):
        for code,(started,id) in list(self.holds.items()):
            if not self.focus or self.focus.id!=id:self.holds.pop(code,None);continue
            if self.clock()-started<self.profile['hold_seconds']:continue
            self.holds.pop(code,None)
            if code==A:
                if self.focus.action=='stat' and self.state.get('stat_points',0)==0:continue
                if self.focus.action=='skill' and self.state.get('skill_points',0)==0:continue
                self.emit('click',self.point(),1,[])
            elif code==X:
                if self.item() and self.item()['owned']:
                    info=metadata(self.profile,self.item())
                    if self.focus.group=='inventory' and info and (info['kind'] in ('weapons','armor') or info['type'] in ('amu','ring')):self.equip_item()
                    elif self.focus.group=='equipment':self.unequip_item()
                    else:self.emit('click',self.point(),3,[])
                elif self.focus.action=='hold_click':self.emit('click',self.point(),1,[])
            elif code==Y:self.quick_move()
        self.advance_transaction()

    def equip_item(self):
        item=self.item();info=metadata(self.profile,item)
        body=4 if info['kind']=='weapons' else {'helm':1,'circ':1,'pelt':1,'phlm':1,'tors':3,'shie':5,'ashd':5,'head':5,
            'glov':10,'boot':9,'belt':8,'amu':2,'ring':6}.get(info['type'])
        if not body:self.message='Equip this item with A';return
        if not self.state.get('complete') or self.state['cursor_type']==4:return
        equipped={u['body']:u for u in self.state['items'] if u['owned'] and u['mode']==1}
        if body==6 and body in equipped and 7 not in equipped:body=7
        displaced=equipped.get(body);return_point=None
        if displaced:
            cell=free_cell(self.profile,'inventory',[u for u in self.state['items'] if u['id']!=item['id']],displaced)
            if cell is None:self.message='Make room for equipped item';return
            g=self.profile['grids']['inventory'];return_point=tuple(round(g['origin'][i]+g['cell'][i]*(cell[i]+.5)) for i in range(2))
        node=next((n for n in self.nodes if n.group=='equipment' and n.data['body']==body),None)
        if not node:return
        self.origin=self.point();self.transaction=dict(id=item['id'],source=self.origin,destination=node.point,phase='pickup',deadline=self.clock()+2,
            displaced=displaced['id'] if displaced else None,return_point=return_point,equip=True)
        self.emit('click',self.origin,1,[])

    def unequip_item(self):
        item=self.item()
        if not self.state.get('complete') or self.state['cursor_type']==4:return
        cell=free_cell(self.profile,'inventory',self.state['items'],item)
        if cell is None:self.message='No space';return
        g=self.profile['grids']['inventory'];dest=tuple(round(g['origin'][i]+g['cell'][i]*(cell[i]+.5)) for i in range(2))
        self.origin=self.point();self.transaction=dict(id=item['id'],source=self.origin,destination=dest,phase='pickup',deadline=self.clock()+2)
        self.emit('click',self.origin,1,[])

    def quick_move(self):
        if self.page=='shop' and self.focus and self.focus.group=='shop':
            self.emit('click',self.point(),3,[]);return
        item=self.item()
        if not item or self.state['cursor_type']==4:return
        if not self.state.get('complete',False):self.message='Container state incomplete';return
        if self.page=='shop':
            self.emit('click',self.point(),1 if item['owned'] else 3,['Control_L'] if item['owned'] else []);return
        if self.page not in ('stash','cube'):
            self.message='Open stash or cube to transfer';return
        target=self.page if self.focus.group=='inventory' else 'inventory'
        cell=free_cell(self.profile,target,self.state['items'],item)
        if cell is None:self.message='No space';return
        g=self.profile['grids'][target];dest=(g['origin'][0]+g['cell'][0]*(cell[0]+.5),g['origin'][1]+g['cell'][1]*(cell[1]+.5))
        self.origin=self.point();self.transaction=dict(id=item['id'],source=self.origin,destination=tuple(map(round,dest)),phase='pickup',deadline=self.clock()+2)
        self.emit('click',self.origin,1,[])

    def advance_transaction(self):
        t=self.transaction;s=self.state
        if not t or not s:return
        if self.clock()>t['deadline']:
            if s['cursor_type']==4 and s['cursor_id']==t['id']:self.emit('click',t['source'],1,[])
            self.transaction=None;self.message='Transfer timed out';return
        if t['phase']=='pickup' and s['cursor_type']==4 and s['cursor_id']==t['id']:
            self.emit('click',t['destination'],1,[]);t['phase']='place';t['deadline']=self.clock()+2
        elif t['phase']=='place' and t.get('displaced') and s['cursor_type']==4 and s['cursor_id']==t['displaced']:
            self.emit('click',t['return_point'],1,[]);t['phase']='return';t['deadline']=self.clock()+2
        elif t['phase'] in ('place','return') and s['cursor_type']==6:
            self.transaction=None;self.message='Equipped' if t.get('equip') else 'Transferred'

    def snapshot(self):
        return dict(page=self.page,focus=self.focus.id if self.focus else None,rect=self.focus.rect if self.focus else None,
                    tab=self.tab,transaction=self.transaction,message=self.message,cursor_mode=self.cursor_mode,keyboard=self.keyboard[self.text_index] if self.text_keyboard else None)
