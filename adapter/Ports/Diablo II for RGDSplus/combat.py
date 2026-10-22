"""Semantic combat buttons. Edges survive short taps and wait for native ACK."""
from collections import deque

BUTTONS={304:1,305:2,307:3,309:4}  # south, east, west, R1
L1,R2=308,315

class CombatInput:
    def __init__(self):
        self.buttons={}; self.edges=[]; self.queue=deque(); self.serial=0
        self.suppressed=set(); self.allowed=False

    def feed(self,code,value):
        previous=self.buttons.get(code,False)
        self.buttons[code]=bool(value)
        if value in (0,1) and previous!=bool(value): self.edges.append((code,bool(value),self.buttons.get(R2,False)))

    def command(self,allowed,ack=0):
        # A held button must be released before crossing UI/touch/legacy modes.
        if allowed!=self.allowed:
            self.queue.clear()
            self.suppressed.update(code for code,held in self.buttons.items() if held)
        self.allowed=allowed
        routed=[]
        for code,down,layer in self.edges:
            if not down: self.suppressed.discard(code)
            if code not in BUTTONS: continue
            if layer:
                if down:self.suppressed.add(code)
                continue
            if allowed:
                if down and code not in self.suppressed:
                    self.serial=(self.serial+1)&0xffffff or 1
                    if len(self.queue)<16: self.queue.append((self.serial<<8)|BUTTONS[code])
            else: routed.append((code,down))
        self.edges.clear()
        while self.queue and self.queue[0]>>8==ack: self.queue.popleft()
        held=0
        if allowed and not self.buttons.get(R2,False):
            for code,bit in ((304,1),(305,2),(L1,4)):
                if self.buttons.get(code,False) and code not in self.suppressed: held|=bit
        return held,(self.queue[0] if allowed and self.queue else 0),routed

    def cancel(self):
        self.queue.clear(); self.edges.clear()
        self.suppressed.update(code for code,held in self.buttons.items() if held)
