"""Modal lower-screen keyboard; characters still go through native X11 input."""
class TouchKeyboard:
    panel = (20, 156, 984, 470)
    close_rect = (852, 168, 136, 42)
    case_rect = (704, 168, 136, 42)
    open_rect = (804, 16, 200, 46)

    def __init__(self, logic):
        self.logic = logic
        self.edit = None
        self.seen_edit = None
        self.contact = False
        self.pressed = None
        self.events=[]

    @staticmethod
    def inside(point, rect):
        x, y = point
        left, top, width, height = rect
        return left <= x < left + width and top <= y < top + height

    @staticmethod
    def key_rect(index):
        return (35 + index % 10 * 96, 246 + index // 10 * 78, 90, 68)

    def sync(self, gui, world):
        controls = (gui or {}).get('controls', [])
        edit = next((c for c in controls if c['type'] == 1 and c['flags'] & 1 and c['flags'] & 4), None)
        if world or self.logic.page != 'frontend':
            edit = None
        identity = edit['id'] if edit else None
        if identity != self.seen_edit:
            self.contact = False
            self.pressed = None
            if self.edit:
                self.logic.text_keyboard = False
            self.edit = edit
            self.seen_edit = identity
            if edit:
                self.show()
        else:
            self.edit = edit

    def show(self):
        if self.edit:
            x, y, width, height = self.edit['rect']
            self.logic.emit('click', (round(x + width / 2), round(y + height / 2)), 1, [])
        self.logic.text_keyboard = True
        self.logic.last_input = self.logic.clock()

    def hit(self, point):
        if self.inside(point, self.close_rect):
            return 'close'
        if self.inside(point, self.case_rect):
            return 'case'
        for index in range(len(self.logic.keyboard)):
            if self.inside(point, self.key_rect(index)):
                return index
        return None

    def touch(self, down, point, logical_size):
        if down is None:
            consumed = self.contact
            self.contact = False
            self.pressed = None
            return consumed
        if not self.contact:
            if not down:
                return False
            if not self.logic.text_keyboard:
                native = (point[0] * logical_size[0] / 1024, point[1] * logical_size[1] / 768)
                if not self.edit or not (self.inside(point, self.open_rect) or self.inside(native, self.edit['rect'])):
                    return False
                self.show()
                self.contact = True
                self.pressed = 'open'
                return True
            self.contact = True
            self.pressed = self.hit(point)
            return True
        if down:
            return True
        pressed = self.pressed
        self.contact = False
        self.pressed = None
        if pressed != self.hit(point):
            return True
        self.events=(self.events+[pressed])[-20:]
        if pressed == 'close':
            self.logic.text_keyboard = False
        elif pressed == 'case':
            self.logic.uppercase = not self.logic.uppercase
        elif isinstance(pressed, int):
            self.logic.text_index = pressed
            self.logic.keyboard_key(self.logic.keyboard[pressed])
        self.logic.last_input = self.logic.clock()
        return True
