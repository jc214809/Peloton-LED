# python file: display/ui/manager.py

import time
from typing import Callable, Dict, Optional, Any
from .screen import Screen
from .login_indicator import draw_login_indicator
from .stale_indicator import draw_stale_indicator
from utils import debug

class ScreenManager:
    def __init__(self, matrix, initial: Optional[Screen] = None,
                 login_required: Optional[Callable[[], bool]] = None,
                 stale_data: Optional[Callable[[], bool]] = None):
        self.matrix = matrix
        self.current: Optional[Screen] = initial
        self.current_name: Optional[str] = None
        self.screens: Dict[str, Screen] = {}
        self._frame_canvas = None
        self.last_tick = time.time()
        self.login_required = login_required or (lambda: False)
        self.stale_data = stale_data or (lambda: False)

        # Call on_enter for the initial screen and ensure display is clean.
        try:
            if self.current is not None:
                self.current.on_enter(self.matrix, None)
        except Exception:
            debug.exception("Error during on_enter of initial screen")
        try:
            self.matrix.Clear()
        except Exception:
            debug.exception("Failed to clear matrix during manager init")

    def register(self, name: str, screen: Screen):
        self.screens[name] = screen

    def show(self, name: str, state: Optional[Any] = None):
        if name not in self.screens:
            debug.error("Screen %s not registered", name)
            return

        try:
            if self.current is not None:
                self.current.on_exit(self.matrix)
        except Exception:
            debug.exception("Error during on_exit of %s", getattr(self.current, "__class__", "?"))

        self.current = self.screens[name]
        self.current_name = name
        self.last_tick = time.time()

        try:
            self.current.on_enter(self.matrix, state)
        except Exception:
            debug.exception("Error during on_enter of %s", name)

    def tick(self, state: Optional[Any] = None):
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        needs_login = self.login_required()
        is_stale = self.stale_data()
        if isinstance(state, dict):
            state = {**state, "login_required": needs_login, "data_stale": is_stale}
        atomic = (getattr(self.current, 'atomic_frames', False) is True
                  and callable(getattr(self.matrix, 'CreateFrameCanvas', None))
                  and callable(getattr(self.matrix, 'SwapOnVSync', None)))
        target = self.matrix
        try:
            if atomic:
                if self._frame_canvas is None:
                    self._frame_canvas = self.matrix.CreateFrameCanvas()
                target = self._frame_canvas
                target.Clear()
            if self.current is not None:
                self.current.update(dt)
                self.current.render(target, state)
        except Exception:
            debug.exception("Error while rendering screen %s", self.current_name)
        if needs_login:
            draw_login_indicator(target)
        if is_stale:
            draw_stale_indicator(target)
        if atomic:
            self._frame_canvas = self.matrix.SwapOnVSync(target)
