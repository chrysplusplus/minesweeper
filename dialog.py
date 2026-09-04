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
from boxsym import L_ew, L_ns, C_es, C_sw, C_nw, C_ne
from util import left_pad_text_to_width

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

    @property
    def padview(self) -> tui.PadView:
        """Return PadView from TextWindow"""
        assert self.textwindow.padview is not None
        return self.textwindow.padview

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing window"""
        pv = self.padview
        win.erase()
        _, maxx = win.getmaxyx()

        lines = self.get_content()
        width = min(max(len(line) for line in lines) + 2, maxx)
        inner_width = width - 2

        format_string = "{left}{inner}{right}"

        y = 0
        win.addstr(y, 0, format_string.format(
            left = C_es,
            inner = L_ew * inner_width,
            right = C_sw))
        y += 1

        for line in lines:
            win.addstr(y, 0, format_string.format(
                left = L_ns,
                inner = left_pad_text_to_width(line[:inner_width], inner_width),
                right = L_ns))
            y += 1

        win.addstr(y, 0, format_string.format(
            left = C_ne,
            inner = L_ew * inner_width,
            right = C_nw))

        area_height = self.default_height if self.default_height is not None else curses.LINES
        area_height = min(area_height, curses.LINES)
        area_width = self.default_width if self.default_width is not None else curses.COLS
        area_width = min(area_width, curses.COLS)

        sy = (area_height - y) // 2
        sx = (area_width - width) // 2
        pv.desired_view_size = (y, width - 1)
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

    def get_content(self) -> list[str]:
        """Get text content for the dialog box"""
        lines = [line for line in self.message]
        lines.append("")
        lines += [option.text for option in self.options]
        return lines

    def reposition_cursor(self):
        """Reposition the screen cursor to the selection"""
        stdwin = self.textwindow.stdwin
        sy, sx = self.padview.desired_screen_start
        cy = len(self.message) + self.choice + sy + 2
        stdwin.stdcurs.cursor = (cy, sx + 1)
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
