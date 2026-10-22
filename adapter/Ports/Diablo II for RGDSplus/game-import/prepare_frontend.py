import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import ctypes
from PIL import Image, ImageDraw, ImageFilter
import frontend_decode as module


def without_baked_title(background):
    mask = Image.new('L',background.size,0)
    for row in range(174,242):
        for column in range(228,572):
            red,green,blue,alpha = background.getpixel((column,row))
            if red>75 and red>green*1.18 and green>blue*1.3:
                mask.putpixel((column,row),255)
    ImageDraw.Draw(mask).rectangle((578,80,589,98),fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(5))
    result = background.copy()
    for row in range(72,246):
        for column in range(224,596):
            if not mask.getpixel((column,row)):
                continue
            donors = []
            for delta_x,delta_y in ((0,-1),(0,1),(-1,0),(1,0)):
                for distance in range(1,33):
                    point = column+delta_x*distance,row+delta_y*distance
                    if not mask.getpixel(point):
                        donors.append((background.getpixel(point),1/distance**2))
                        break
            if not donors:
                raise ValueError('Cannot restore title background beneath lettering')
            weight = sum(item[1] for item in donors)
            result.putpixel((column,row),tuple(round(sum(color[index]*amount for color,amount in donors)/weight) for index in range(3))+(255,))
    return result


def _generate(decoded,output):
    ASSETS = Path(decoded)
    DESTINATION = Path(__file__).with_name('frontend')
    assets = Path(output)
    assets.mkdir()
    pages = {}
    palette_data = (ASSETS/'units-palette.dat').read_bytes()
    palette = []
    for index in range(256):
        blue,green,red = palette_data[index*3:index*3+3]
        palette.extend((red,green,blue))
    mappings = [('title-screen','trademarkscreenEXP','sky'),
                ('main-menu','gameselectscreenEXP','sky'),
                ('character-select','characterselectscreenEXP','sky'),
                ('character-create','charactercreationscreenEXP','fechar')]
    backgrounds = {}
    for name, stem, palette_name in mappings:
        palette_data = (ASSETS/(palette_name+'-palette.dat')).read_bytes()
        colors = []
        for index in range(256):
            blue,green,red = palette_data[index*3:index*3+3]
            colors.extend((red,green,blue))
        canvas = Image.new('RGBA',(800,600),(0,0,0,255))
        for index,frame in enumerate(module.frames((ASSETS/(stem+'.dc6')).read_bytes())):
            width,height,offset_x,offset_y,pixels,alpha = frame
            tile = Image.frombytes('P',(width,height),pixels)
            tile.putpalette(colors)
            canvas.paste(tile.convert('RGBA'),((index%4)*256,(index//4)*256))
        filename = name+'.bgra'
        (assets/filename).write_bytes(canvas.tobytes('raw','BGRA'))
        canvas.save(ASSETS/(name+'-reference.png'))
        backgrounds[name] = canvas
        pages[name] = {'background':filename,'originalSize':[800,600]}
        if name == 'main-menu':
            pages[name]['logoErase'] = [210,0,380,236]
    main_background = backgrounds['main-menu']
    selection_background = backgrounds['character-select']
    subtitle_bounds = (235,180,565,236)
    subtitle = main_background.crop(subtitle_bounds)
    mask = Image.new('L',subtitle.size,0)
    for row in range(subtitle.height):
        for column in range(subtitle.width):
            red,green,blue,alpha = subtitle.getpixel((column,row))
            if red>75 and red>green*1.18 and green>blue*1.3:
                mask.putpixel((column,row),255)
    subtitle.putalpha(mask.filter(ImageFilter.MaxFilter(3)))
    (assets/'subtitle.bgra').write_bytes(subtitle.tobytes('raw','BGRA'))
    subtitle.save(ASSETS/'subtitle.png')
    clean = main_background.copy()
    ratios = []
    for row in (*range(150,174),*range(242,266)):
        for column in range(228,572):
            original = main_background.getpixel((column,row))
            dimmed = selection_background.getpixel((column,row))
            ratios.extend(first/second for first,second in zip(original[:3],dimmed[:3])
                          if 12<=second<=64 and 1.5<=first/second<=3)
    brightness = statistics.median(ratios)
    for left,top,right,bottom in ((228,174,572,242),(570,74,596,104)):
        for row in range(top,bottom):
            for column in range(left,right):
                point = column,row
                original = main_background.getpixel(point)
                dimmed = selection_background.getpixel(point) if top==174 else tuple(value/brightness for value in main_background.getpixel((column,row-30)))
                weight = min(1,min(column-left,right-column-1,row-top,bottom-row-1)/4)
                restored = tuple(round(original[index]*(1-weight)+min(255,dimmed[index]*brightness)*weight) for index in range(3))+(255,)
                clean.putpixel(point,restored)
    (assets/'main-menu-clean.bgra').write_bytes(clean.tobytes('raw','BGRA'))
    clean.save(ASSETS/'main-menu-clean.png')
    pages['main-menu']['lowerBackground'] = 'main-menu-clean.bgra'
    pages['main-menu']['logoErase'] = [210,0,380,248]
    title = without_baked_title(backgrounds['title-screen'])
    (assets/'title-screen-clean.bgra').write_bytes(title.tobytes('raw','BGRA'))
    title.save(ASSETS/'title-screen-clean.png')
    pages['title-screen']['lowerBackground'] = 'title-screen-clean.bgra'
    pages['title-screen']['logoErase'] = [210,0,390,248]
    lines = ('Diablo II for RGDSplus','移植by Blood_roc')
    credit = Image.frombytes('RGBA',(174,48),(DESTINATION/'credit.bgra').read_bytes(),'raw','BGRA')
    (assets/'credit.bgra').write_bytes(credit.tobytes('raw','BGRA'))
    upper_art = {'title-screen':'title-upper-v2',
                 'main-menu':'main-upper-v1',
                 'character-select':'main-upper-v1',
                 'character-create':'creation-upper-v2'}
    for name,item in pages.items():
        stem = upper_art[name]
        image_path = DESTINATION/'art'/(stem+'.png')
        image = Image.open(image_path).convert('RGBA')
        filename = stem+'.bgra'
        (assets/filename).write_bytes(image.tobytes('raw','BGRA'))
        item['upper'] = filename
        item['upperSize'] = list(image.size)
        item['upperOrigin'] = 'new-extension-art-not-hidden-original-scenery'
    decoded = {}
    for side in ('BlackLeft','BlackRight','FireLeft','FireRight'):
        decoded[side] = module.frames((ASSETS/('D2logo'+side+'.dc6')).read_bytes())
    canvases = []
    for frame_index in range(30):
        canvas = Image.new('RGBA',(400,220),(0,0,0,0))
        for side in ('BlackLeft','BlackRight','FireLeft','FireRight'):
            width,height,offset_x,offset_y,pixels,alpha = decoded[side][frame_index]
            image = Image.frombytes('P',(width,height),pixels)
            image.putpalette(palette)
            image = image.convert('RGBA')
            image.putalpha(Image.frombytes('L',(width,height),alpha))
            canvas.alpha_composite(image,(200+offset_x,160-height+offset_y))
        canvases.append(canvas)
    bounds = [canvas.getbbox() for canvas in canvases]
    union = (min(bounds[0] for bounds in bounds),min(bounds[1] for bounds in bounds),
             max(bounds[2] for bounds in bounds),max(bounds[3] for bounds in bounds))
    canvases = [canvas.crop(union) for canvas in canvases]
    animation = b''.join(canvas.tobytes('raw','BGRA') for canvas in canvases)
    canvases[0].save(ASSETS/'logo-composite.png')
    (assets/'logo.bgra').write_bytes(animation)
    manifest = {'schema':1,'pages':pages,'logo':{'file':'logo.bgra','frames':30,'size':list(canvases[0].size)},
                'subtitle':{'file':'subtitle.bgra','size':list(subtitle.size),'gap':12},
                'credit':{'file':'credit.bgra','size':list(credit.size),'lines':list(lines),'right':20,'top':20},
                'privateDerivedResources':True,'generatedBy':'game-import/prepare_frontend.py'}
    referenced = {item[key] for item in pages.values()
                  for key in ('background','lowerBackground','upper') if key in item}
    referenced.update(manifest[key]['file'] for key in ('logo','subtitle','credit'))
    manifest['files'] = {name:hashlib.sha256((assets/name).read_bytes()).hexdigest()
                         for name in sorted(referenced)}
    expected = json.loads((DESTINATION/'recipe.json').read_text(encoding='utf-8'))
    if manifest['files']!=expected['files']:
        raise ValueError('Generated frontend pixels differ from the tested device version')
    (assets/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest

def generate(gamedata,output):
    handles = []
    try:
        for name in ('Patch_D2.mpq','d2exp.mpq','d2data.mpq'):
            handle = ctypes.c_void_p()
            if not module.storm.lib.SFileOpenArchive(str(Path(gamedata)/name),0,0x100,ctypes.byref(handle)):
                raise OSError('Cannot open imported archive: '+name)
            handles.append(handle)
        def read(name):
            for handle in handles:
                try:
                    return module.read(handle,name)
                except FileNotFoundError:
                    pass
            raise FileNotFoundError(name)
        with tempfile.TemporaryDirectory(prefix='d2-frontend-') as directory:
            decoded = Path(directory)
            for name in ('sky','fechar','units'):
                (decoded/(name+'-palette.dat')).write_bytes(read('data\\global\\palette\\'+name+'\\pal.dat'))
            for name in ('trademarkscreenEXP','gameselectscreenEXP','characterselectscreenEXP',
                         'charactercreationscreenEXP','D2logoBlackLeft','D2logoBlackRight','D2logoFireLeft','D2logoFireRight'):
                folder = 'CharSelect' if name=='characterselectscreenEXP' else 'FrontEnd'
                (decoded/(name+'.dc6')).write_bytes(read('data\\global\\ui\\'+folder+'\\'+name+'.dc6'))
            return _generate(decoded,output)
    finally:
        for handle in handles:
            module.storm.lib.SFileCloseArchive(handle)
