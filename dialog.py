"""File: dialog.py
Author: chrysplusplus
Date: 2026-08-30

Module containing types for displaying dialogs within a TUI application"""

import curses

from collections.abc import Callable
from dataclasses import dataclass, KW_ONLY
from typing import Protocol

import tui
from event import BaseEvent

class DialogLike(Protocol):
    """Protocol defining requirements of a dialog-like type"""
    textwindow: tui.TextWindow

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing"""

    def bind_events(self):
        """Bind dialog events"""

    def unbind_events(self):
        """Unbind dialog events"""

@dataclass(slots = True)
class MovementEvent(BaseEvent):
    """Event class for movement keys"""
    _: KW_ONLY
    x: int = 0
    y: int = 0
    relative: bool = True

    def get_moved_coords_from(self, from_coords: tuple[int, int]) -> tuple[int, int]:
        """Return the new coords after movement from initial coords"""
        fromx, fromy = from_coords
        if self.relative:
            return (fromx + self.x, fromy + self.y)
        return (self.x, self.y)

@dataclass(slots = True)
class SelectEvent(BaseEvent):
    """Event class for activating the current selection"""

@dataclass(slots = True)
class QuitEvent(BaseEvent):
    """Event class for the user quitting the program"""
    _: KW_ONLY
    confirm_dialog: DialogLike | None = None

@dataclass(slots = True)
class OpenDialogEvent(BaseEvent):
    """Event class for opening a dialog"""
    dialog: DialogLike

@dataclass(slots = True)
class DialogRestoreEvent(BaseEvent):
    """Event class for restoring from a dialog"""
    dialog: DialogLike

@dataclass(slots = True)
class Option:
    """Parameters for option entry in OptionsDialog"""
    text: str
    callback: Callable[[], None] | None = None
    _: KW_ONLY
    do_restore: bool = False

@dataclass(slots = True)
class OptionsDialog:
    """Overlaying options dialog box"""
    textwindow: tui.TextWindow
    message: list[str]
    options: list[Option]
    _: KW_ONLY
    choice: int = 0
    default_width: int | None = None
    default_height: int | None = None
    on_restore: Callable[[], None] | None = None

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing window"""
        pv = self.textwindow.padview
        assert pv is not None
        win.erase()
        _, maxx = win.getmaxyx()

        y = 0
        width = 0

        for line in self.message:
            trimmed = line[:maxx]
            width = max(width, len(trimmed))
            win.addstr(y, 0, trimmed)
            y += 1

        y += 1

        for option in self.options:
            line = option.text[:maxx]
            width = max(width, len(line))
            win.addstr(y, 0, line)
            y += 1

        y -= 1

        area_height = self.default_height if self.default_height is not None else curses.LINES
        area_height = min(area_height, curses.LINES)
        area_width = self.default_width if self.default_width is not None else curses.COLS
        area_width = min(area_width, curses.COLS)

        sy = (area_height - y) // 2
        sx = (area_width - width) // 2
        pv.desired_view_size = (y, width)
        pv.desired_screen_start = (sy, sx)

        self.reposition_cursor()
        return True

    def on_selection_changed(self, e: MovementEvent):
        """Callback to changing the selection"""
        delta = e.x if e.x != 0 else e.y
        self.choice = (self.choice + delta) % len(self.options)
        self.reposition_cursor()

    def on_select(self, _):
        """Callback for selecting an option"""
        assert self.choice < len(self.options)
        selection = self.options[self.choice]
        if selection.callback is not None:
            selection.callback()

        if selection.do_restore:
            self.textwindow.event_handler.enqueue(DialogRestoreEvent(self))

    def reposition_cursor(self):
        """Reposition the screen cursor to the selection"""
        stdwin = self.textwindow.stdwin
        sy, sx = self.textwindow.padview.desired_screen_start
        cy = len(self.message) + self.choice + sy + 1
        stdwin.stdcurs.cursor = (cy, sx)
        stdwin.move_cursor(stdwin.stdcurs)

    def bind_events(self):
        """Bind events for option dialog"""
        event_handler = self.textwindow.event_handler
        event_handler.bind(MovementEvent, self.on_selection_changed)
        event_handler.bind(SelectEvent, self.on_select)

    def unbind_events(self):
        """Unbind events after use"""
        event_handler = self.textwindow.event_handler
        event_handler.unbind(MovementEvent)
        event_handler.unbind(SelectEvent)

# vim: foldmethod=indent foldnestmax=2 foldlevel=2
