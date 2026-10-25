"""Optional frontend composition, separate from the unchanged world renderer."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import statistics
import time


class FrontendPanels:
    def __init__(self, sdl, upper, lower, rect_type, directory, report_path=None):
        self.sdl = sdl
        self.upper = upper
        self.lower = lower
        self.Rect = rect_type
        self.directory = Path(directory)
        self.report_path = Path(report_path) if report_path else None
        self.manifest = json.loads((self.directory/'manifest.json').read_text())
        for name,expected in self.manifest['files'].items():
            path = self.directory/name
            if path.parent != self.directory or path.is_symlink():
                raise ValueError('Unsafe frontend resource path')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Frontend resource hash mismatch: '+name)
        self.backgrounds = {}
        self.textures = []
        self.logo_frames = []
        self.page = None
        self.inferred = False
        self.frame = None
        self.started = time.monotonic()
        self.last_report = 0
        self.scores = {}
        self.gains = {}
        self.anchors = [(column,row) for row in (8,32,64,128,192,256,384,560)
                        for column in (8,24,64,128,192,608,704,776,792)]
        for name, item in self.manifest['pages'].items():
            pixels = (self.directory/item['background']).read_bytes()
            if len(pixels) != 800*600*4:
                raise ValueError('Invalid frontend background: '+name)
            samples = [pixels[(row*800+column)*4:(row*800+column)*4+3]
                       for column,row in self.anchors]
            self.backgrounds[name] = {'pixels':pixels, 'samples':samples,
                                      'gain':1.0}
            lower_pixels = (self.directory/item.get('lowerBackground',item['background'])).read_bytes()
            if len(lower_pixels)!=800*600*4:
                raise ValueError('Invalid lower background')
            self.backgrounds[name]['lowerPixels'] = lower_pixels
            self.backgrounds[name]['lower'] = self.texture(lower,800,600,lower_pixels)
            extension = item.get('upper')
            if extension:
                pixels = (self.directory/extension).read_bytes()
                width,height = item['upperSize']
                if not 0<width<=2048 or not 0<height<=2048 or len(pixels) != width*height*4:
                    raise ValueError('Invalid frontend extension: '+name)
                self.backgrounds[name]['upper'] = self.texture(upper,width,height,pixels)
                self.backgrounds[name]['upperPixels'] = pixels
                self.backgrounds[name]['upperSize'] = width,height
        width,height = self.manifest['logo']['size']
        data = (self.directory/self.manifest['logo']['file']).read_bytes()
        frame_size = width*height*4
        if len(data) != frame_size*self.manifest['logo']['frames']:
            raise ValueError('Invalid frontend logo animation')
        for offset in range(0,len(data),frame_size):
            texture = self.texture(upper,width,height,data[offset:offset+frame_size])
            if self.sdl.SDL_SetTextureBlendMode(texture,1) != 0:
                raise RuntimeError('Cannot enable logo alpha blending')
            self.logo_frames.append(texture)
        self.subtitle = self.alpha_texture(self.manifest['subtitle'])
        self.credit = self.alpha_texture(self.manifest['credit'],lower)

    def alpha_texture(self, item, renderer=None):
        width,height = item['size']
        data = (self.directory/item['file']).read_bytes()
        if len(data)!=width*height*4:
            raise ValueError('Invalid title/credit texture')
        texture = self.texture(renderer or self.upper,width,height,data)
        if self.sdl.SDL_SetTextureBlendMode(texture,1)!=0:
            raise RuntimeError('Cannot blend title/credit texture')
        return texture

    def texture(self, renderer, width, height, pixels):
        texture = self.sdl.SDL_CreateTexture(renderer,0x16362004,0,width,height)
        if not texture:
            raise RuntimeError('Cannot allocate frontend texture')
        self.textures.append(texture)
        buffer = C.create_string_buffer(pixels)
        if self.sdl.SDL_UpdateTexture(texture,None,buffer,width*4) != 0:
            raise RuntimeError('Cannot upload frontend texture')
        return texture

    def classify(self, size, address, pitch, gui=None):
        if size != (800,600) or not self.lower:
            self.page = None
            self.inferred = False
            return None
        samples = [C.string_at(address+row*pitch+column*4,3)
                   for column,row in self.anchors]
        controls = gui.get('controls',[]) if gui and 0<=time.monotonic_ns()-gui.get('stamp',0)<800_000_000 else []
        def has(kind, bounds):
            return any(item['type']==kind and item['rect']==bounds for item in controls)
        if has(6,[264,289,272,35]):
            native_page = 'main-menu'
        elif has(6,[33,468,168,60]):
            native_page = 'character-select'
        elif has(1,[318,494,157,16]) and has(6,[33,537,128,35]):
            native_page = 'character-create'
        elif len(controls)==1 and has(4,[100,500,600,80]):
            native_page = 'title-screen'
        else:
            native_page = None
        scores = {}
        for name, background in self.backgrounds.items():
            ratios = [actual/expected for first,second in zip(samples,background['samples'])
                      for actual,expected in zip(first,second)
                      if 24<=expected<=160 and 4<=actual<=248 and .5<=actual/expected<=2.5]
            gain = statistics.median(ratios) if ratios else 1.0
            pairs = [(actual,expected) for first,second in zip(samples,background['samples'])
                     for actual,expected in zip(first,second)
                     if 24<=expected<=160 and abs(actual-expected*gain)<=2]
            if pairs:
                gain = round(sum(actual*expected for actual,expected in pairs)/sum(expected*expected for _,expected in pairs),2)
            matches = sum(max(abs(first[index]-min(255,int(second[index]*gain))) for index in range(3)) <= 6
                          for first,second in zip(samples,background['samples']))
            scores[name] = matches/len(samples)
            self.gains[name] = gain
        page = native_page if native_page and scores[native_page] >= .50 else None
        inferred = False
        if page is None and native_page is None:
            menu_pages = ('main-menu','character-select')
            other_score = max(scores[name] for name in scores if name not in menu_pages)
            menu_page = max(menu_pages,key=scores.get)
            if scores[menu_page] >= .65 and scores[menu_page]-other_score >= .20:
                page = menu_page
                inferred = True
        self.inferred = inferred
        if page and abs(self.gains[page]-self.backgrounds[page]['gain'])>=.03:
            background = self.backgrounds[page]
            gain = self.gains[page]
            lookup = bytes(min(255,int(value*gain)) for value in range(256))
            buffer = C.create_string_buffer(background['lowerPixels'].translate(lookup))
            if self.sdl.SDL_UpdateTexture(background['lower'],None,buffer,3200) != 0:
                raise RuntimeError('Cannot match native frontend brightness')
            if background.get('upper'):
                buffer = C.create_string_buffer(background['upperPixels'].translate(lookup))
                width,height = background['upperSize']
                if self.sdl.SDL_UpdateTexture(background['upper'],None,buffer,width*4) != 0:
                    raise RuntimeError('Cannot match extension brightness')
            background['gain'] = gain
        if page != self.page:
            detail=' background-fallback' if inferred else ''
            print('FRONTEND: page='+str(page)+detail+' matches='+str(scores),flush=True)
        self.page = page
        self.scores = scores
        self.report()
        return page

    def report(self):
        now = time.monotonic()
        if self.report_path and now-self.last_report >= .25:
            background = self.backgrounds.get(self.page,{})
            report = {'stamp':time.monotonic_ns(),'page':self.page,'inferred':self.inferred,'logoFrame':self.frame,
                      'backgroundScores':self.scores,'brightnessGains':self.gains,
                      'extension':bool(background.get('upper'))}
            path = self.report_path
            temporary = path.with_suffix('.next')
            try:
                temporary.write_text(json.dumps(report))
                temporary.replace(path)
            except OSError as error:
                self.report_path = None
                print('FRONTEND: diagnostic report disabled: '+str(error),flush=True)
            self.last_report = now

    def draw(self):
        if self.page is None:
            return
        background = self.backgrounds[self.page]
        destination = self.Rect(0,0,1024,768)
        if background.get('upper'):
            self.sdl.SDL_RenderCopy(self.upper,background['upper'],None,C.byref(destination))
        if not self.inferred and 'logoErase' in self.manifest['pages'][self.page]:
            source = self.Rect(*self.manifest['pages'][self.page]['logoErase'])
            target = self.Rect(round(source.x*1.28),round(source.y*1.28),
                               round(source.w*1.28),round(source.h*1.28))
            self.sdl.SDL_RenderCopy(self.lower,background['lower'],C.byref(source),C.byref(target))
        index = int((time.monotonic()-self.started)*25)%len(self.logo_frames)
        width,height = self.manifest['logo']['size']
        subtitle_width,subtitle_height = self.manifest['subtitle']['size']
        gap = self.manifest['subtitle']['gap']
        group_height = height+gap+subtitle_height
        group_top = (768-group_height*1.28)/2
        destination = self.Rect(round((1024-width*1.28)/2),round(group_top),
                                round(width*1.28),round(height*1.28))
        self.sdl.SDL_RenderCopy(self.upper,self.logo_frames[index],None,C.byref(destination))
        destination = self.Rect(round((1024-subtitle_width*1.28)/2),round(group_top+(height+gap)*1.28),
                                round(subtitle_width*1.28),round(subtitle_height*1.28))
        self.sdl.SDL_RenderCopy(self.upper,self.subtitle,None,C.byref(destination))
        if self.page=='main-menu' and not self.inferred:
            credit = self.manifest['credit']
            width,height = credit['size']
            destination = self.Rect(1024-credit['right']-width,credit['top'],width,height)
            self.sdl.SDL_RenderCopy(self.lower,self.credit,None,C.byref(destination))
        self.frame = index
        self.report()

    def close(self):
        for texture in self.textures:
            self.sdl.SDL_DestroyTexture(texture)
        self.textures.clear()
