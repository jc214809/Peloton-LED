# python file: display/ui/manager.py

import time
from typing import Dict, Optional
from .screen import Screen

class ScreenManager:
    def __init__(self, matrix, initial: Screen):
        self.matrix = matrix
        self.current: Screen = initial
        self.screens: Dict[str, Screen] = {}
        self.last_tick = time.time()

    def register(self, name: str, screen: Screen):
        self.screens[name] = screen

    def show(self, name: str):
        self.current = self.screens[name]

    def tick(self):
        # call update and render; central place to Clear() and maybe double-buffer
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        try:
            self.current.update(dt)
            self.current.render(self.matrix)
        except Exception:
            # handle hardware-dependent errors
            pass