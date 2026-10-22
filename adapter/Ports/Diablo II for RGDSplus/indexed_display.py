"""Palette expansion on each panel's GLES2 context, with explicit CPU fallback."""
import ctypes as C
import json
import os
from pathlib import Path
import time


class IndexedDisplay:
    def __init__(self, renderers, anchors, width, height):
        self.width, self.height = width, height
        self.lib = C.CDLL(str(Path(__file__).with_name('indexed_gpu.so')))
        def bind(name, result, args):
            f = getattr(self.lib, name); f.restype, f.argtypes = result, args
            return f
        ptr, integer = C.c_void_p, C.c_int
        bind('d2_index_create', ptr, [ptr, ptr, integer, integer])
        bind('d2_index_gpu', C.c_char_p, [ptr])
        bind('d2_index_error', C.c_char_p, [])
        bind('d2_index_upload', integer, [ptr, ptr, ptr])
        bind('d2_index_draw', integer, [ptr, integer, integer])
        bind('d2_index_activate', integer, [ptr])
        bind('d2_index_verify', integer, [ptr, ptr, ptr])
        bind('d2_index_destroy', None, [ptr])
        bind('d2_index_expand', None, [ptr, ptr, ptr, integer])
        self.handles = [self.lib.d2_index_create(r, a, width, height) for r, a in zip(renderers, anchors)]
        self.gpu = all(self.handles)
        self.buffers = [C.create_string_buffer(width*height*4) for _ in range(2)]
        self.report = dict(backend='gles2-indexed' if self.gpu else 'cpu-indexed-fallback',
                           gpu=[self.lib.d2_index_gpu(h).decode() if h else None for h in self.handles],
                           error=None if self.gpu else self.lib.d2_index_error().decode(),
                           width=width, height=height, created=time.time())
        Path('/tmp/d2-classic-gpu-state.json').write_text(json.dumps(self.report))
        print('DISPLAY_INDEXED:', json.dumps(self.report), flush=True)

    def upload(self, upper, lower, palette):
        self.check_ready=False
        if os.environ.get('D2_QA_INPUT')=='1' and Path('/tmp/d2-classic-gpu-check.request').exists():
            self.reference=[C.create_string_buffer(C.string_at(p,self.width*self.height)) for p in (upper,lower)]
            self.reference_palette=C.create_string_buffer(C.string_at(palette,1024))
            self.check_ready=True
        if self.gpu:
            for handle, pixels in zip(self.handles, (upper, lower)):
                result = self.lib.d2_index_upload(handle, pixels, palette)
                if result: raise RuntimeError('Indexed GPU upload failed: '+str(result))
        else:
            for out, pixels in zip(self.buffers, (upper, lower)):
                self.lib.d2_index_expand(pixels, palette, out, self.width*self.height)

    def draw(self, panel, width=1024, height=768):
        result = self.lib.d2_index_draw(self.handles[panel], width, height)
        if result: raise RuntimeError('Indexed GPU draw failed: '+str(result))

    def activate(self, panel):
        if self.lib.d2_index_activate(self.handles[panel]):
            raise RuntimeError('Could not activate panel context before swap')

    def validate(self, upper, lower, palette, sequence):
        request = Path('/tmp/d2-classic-gpu-check.request')
        # A request can arrive between upload and draw. Keep it pending until
        # the next upload captures this frame's exact CPU reference.
        if not self.gpu or os.environ.get('D2_QA_INPUT') != '1' or not request.exists() or not getattr(self,'check_ready',False): return
        request.unlink()
        self.check_ready=False
        checks = [self.lib.d2_index_verify(h, pixels, self.reference_palette) for h, pixels in zip(self.handles, self.reference)]
        result = dict(sequence=sequence, pixels_per_panel=self.width*self.height, mismatches=checks, stamp=time.time())
        path=Path('/tmp/d2-classic-gpu-validation.json')
        try: history=json.loads(path.read_text())
        except (OSError,ValueError): history=[]
        history.append(result);path.write_text(json.dumps(history,indent=2))
        if any(x != 0 for x in checks): raise RuntimeError('GPU palette mismatch: '+str(checks))

    def close(self):
        for h in self.handles:
            if h: self.lib.d2_index_destroy(h)
