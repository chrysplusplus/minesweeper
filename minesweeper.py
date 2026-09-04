#!/usr/bin/env python3

"""Main module for Minesweeper TUI game

Author: chrysplusplus

TODO

- [ ] Ensure game padview and screen are large enough for the grid
- [ ] Implement game logic
    - [X] Lose on revealing a mine
    - [X] Win on revealing last empty tile
    - [X] Fix reveal display bugs
- [ ] Implement settings dialog
- [ ] Add styles for different tiles
"""

import curses

from collections.abc import Callable
from functools import partial
from typing import Any

import tui
import terminal as term

from dialog import MovementEvent, SelectEvent, Option, OptionsDialog
from event import EventHandler
from game import QuitEvent, GameLogic, empty_tile_grid, label_yxcoords, label_xycoords, \
        get_grid_height
from terminal import init_curses
from util import same, compose2

class DebugPanel:
    """Debug window that can override MainWindow on_post_key to update on every
    keypress"""
    __slots__ = ("stdwin", "window", "padview", "drawstate", "is_visible", "update_callback",
                 "track_map")

    def __init__(self, stdwin: tui.MainWindow):
        self.stdwin = stdwin
        self.window = curses.newpad(100, 100)
        self.padview = tui.PadView(self.window)
        self.drawstate = tui.WindowDrawState(self.window)
        self.drawstate.on_draw = self.on_draw
        self.stdwin.add_child(self.drawstate, self.padview)

        self.is_visible = False
        self.update_callback: Callable[[], None] | None = None
        self.track_map = {}

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing the window"""
        pv = self.padview
        assert same(pv.pad, win)
        win.erase()
        if not self.is_visible:
            pv.desired_view_size = (0, 0)
            return True

        maxy, maxx = win.getmaxyx()
        maxx = min(maxx, curses.COLS - 1)
        win.addstr(0, 0, "Debug", term.ATTR_WHITE)
        y = 1
        w = 6
        for key, value in self.track_map.items():
            value_text = value() if callable(value) else value
            line = f"{key}: {value_text}"[:maxx]
            w = max(w, len(line))
            win.addstr(y, 0, line, term.ATTR_WHITE)
            y += 1
            if y == maxy:
                break

        pv.desired_view_size = (y, w)
        return True

    def on_update(self):
        """Callback when enabled for updating after each keypress"""
        if self.update_callback is not None:
            self.update_callback()

        tui.windraw_refresh(self.drawstate, self.padview)
        self.stdwin.move_cursor(self.stdwin.stdcurs)

    def track(self, key: str, value: Any):
        """Add value or callable to map of tracked values"""
        self.track_map[key] = value

    def untrack(self, key: str) -> Any:
        """Remove and return tracked value"""
        return self.track_map.pop(key) if key in self.track_map else None

    def enable(self):
        """Enable the debug display"""
        self.update_callback = self.stdwin.on_post_key
        self.stdwin.on_post_key = self.on_update
        self.is_visible = True
        self.stdwin.refresh()

    def disable(self):
        """Disable the debug display"""
        self.stdwin.on_post_key = self.update_callback
        self.update_callback = None
        self.is_visible = False
        self.stdwin.refresh()

    def toggle(self):
        """Toggle the state of the debug display"""
        if self.is_visible:
            self.disable()
        else:
            self.enable()

class MinesweeperApp:
    """Main application class for marshalling initialisation and program state"""
    __slots__ = ("stdwin", "event_handler", "game_logic", "keyhelp", "overlay", "titlebar",
                 "debug_panel")

    def __init__(self, stdwin: tui.MainWindow):
        self.stdwin = stdwin
        self.event_handler = EventHandler()
        self.stdwin.on_post_key = self.event_handler.process

        self.game_logic = GameLogic(
                stdwin = self.stdwin,
                event_handler = self.event_handler,
                grid = empty_tile_grid((10, 10), 15))
        self.keyhelp = key_instruction_bar(self.stdwin, self.event_handler)
        self.overlay = overlay(self.stdwin, self.event_handler)
        self.titlebar = titlebar(self.stdwin, self.event_handler)
        self.debug_panel = DebugPanel(self.stdwin)
        self.track_values()

        self.game_logic.set_overlay_surface(self.overlay)

        self.stdwin.stdcurs.cursor = (-1, -1)
        self.game_logic.resize_drawing_surface()
        self.stdwin.refresh()

        self.map_window()
        self.map_selection()
        self.game_logic.map_game_controls()
        self.game_logic.start_playing()
        self.stdwin.mainloop()

    def on_resize(self):
        """Callback for window resizing"""
        curses.update_lines_cols()
        self.game_logic.resize_drawing_surface()
        self.stdwin.refresh()

    def on_reset(self):
        """Callback for window reset/refresh"""
        self.stdwin.stdscr.clear()
        self.stdwin.refresh()

    def on_quit(self):
        """Callback for the user quitting the program

        Emits an event that may result in a confirmation dialog being
        displayed"""
        if self.overlay.drawstate.on_draw is not None:
            return

        quit_dialog = OptionsDialog(
                textwindow = self.overlay,
                message = ["Are you sure you want to quit?"],
                options = [
                    Option("Yes", self.do_quit),
                    Option("No", do_restore = True)],
                choice = 1,
                default_height = get_grid_height(self.game_logic.grid.grid_size))

        self.event_handler.enqueue(QuitEvent(confirm_dialog = quit_dialog))

    def do_quit(self):
        """Quit the mainloop"""
        self.stdwin.quit()

    def map_window(self):
        """Map the application keys for controlling the window state, such as
        screen refreshing, debug capabilities and quitting

        By default, quitting is bound to MinesweeperApp.do_quit, which ends the
        mainloop immediately, but this can be rebound by objects that handle
        displaying dialogs"""

        self.stdwin.add_mapping(tui.askey("KEY_RESIZE"), self.on_resize)
        self.stdwin.add_mapping(tui.askey("C-L"), self.on_reset)
        self.stdwin.add_mapping(tui.askey("g"), self.debug_panel.toggle)

        self.event_handler.bind(QuitEvent, lambda _: self.do_quit())
        self.stdwin.add_mapping(tui.askey("C-C"), self.on_quit)
        self.stdwin.add_mapping(tui.askey("q"), self.on_quit)

    def map_selection(self):
        """Map the directional keys to emit movement events"""
        stdwin = self.stdwin
        event_handler = self.event_handler
        stdwin.add_mapping(tui.askey("k"),
                           partial(event_handler.enqueue, MovementEvent(y = -1)))
        stdwin.add_mapping(tui.askey("j"),
                           partial(event_handler.enqueue, MovementEvent(y = 1)))
        stdwin.add_mapping(tui.askey("h"),
                           partial(event_handler.enqueue, MovementEvent(x = -1)))
        stdwin.add_mapping(tui.askey("l"),
                           partial(event_handler.enqueue, MovementEvent(x = 1)))
        stdwin.add_mapping(tui.askey("w"),
                           partial(event_handler.enqueue, MovementEvent(y = -1)))
        stdwin.add_mapping(tui.askey("s"),
                           partial(event_handler.enqueue, MovementEvent(y = 1)))
        stdwin.add_mapping(tui.askey("a"),
                           partial(event_handler.enqueue, MovementEvent(x = -1)))
        stdwin.add_mapping(tui.askey("d"),
                           partial(event_handler.enqueue, MovementEvent(x = 1)))
        stdwin.add_mapping(tui.askey("KEY_UP"),
                           partial(event_handler.enqueue, MovementEvent(y = -1)))
        stdwin.add_mapping(tui.askey("KEY_DOWN"),
                           partial(event_handler.enqueue, MovementEvent(y = 1)))
        stdwin.add_mapping(tui.askey("KEY_LEFT"),
                           partial(event_handler.enqueue, MovementEvent(x = -1)))
        stdwin.add_mapping(tui.askey("KEY_RIGHT"),
                           partial(event_handler.enqueue, MovementEvent(x = 1)))
        stdwin.add_mapping(tui.askey("KEY_ENTER"),
                           partial(event_handler.enqueue, SelectEvent()))
        stdwin.add_mapping(tui.askey("C-J"),
                           partial(event_handler.enqueue, SelectEvent()))

    def track_values(self):
        """Initialise the debug panel with tracked values"""
        self.debug_panel.track("cursor", lambda: self.stdwin.stdcurs)
        self.debug_panel.track("grid_coord", compose2(
            partial(getattr, self.game_logic, "selection"), label_xycoords))

        gameview_pv = self.game_logic.display.padview
        self.debug_panel.track("pv_pad", compose2(
            partial(getattr, gameview_pv, "pad_start"), label_yxcoords))
        self.debug_panel.track("pv_screen", compose2(
            partial(getattr, gameview_pv, "desired_screen_start"), label_yxcoords))
        self.debug_panel.track("pv_view", compose2(
            partial(getattr, gameview_pv, "desired_view_size"), label_yxcoords))

def key_instruction_bar(stdwin: tui.MainWindow, event_handler: EventHandler) -> tui.TextWindow:
    """Object for drawing key instructions"""
    window = curses.newwin(1, curses.COLS, curses.LINES - 1, 0)
    drawstate = tui.WindowDrawState(window)

    def on_draw(win: curses.window) -> bool:
        win.mvwin(curses.LINES - 1, 0)
        _, maxx = win.getmaxyx()
        win.erase()
        text = "KEYS: ←↑↓→/wasd to move; f to place flag; "\
                "Space/Return to check; q/^C to quit"[:maxx - 1]
        win.addstr(0, 0, text)
        return True

    drawstate.on_draw = on_draw
    stdwin.add_child(drawstate)
    return tui.TextWindow(
            stdwin,
            event_handler,
            drawstate)

def overlay(stdwin: tui.MainWindow, event_handler: EventHandler):
    """Object for drawing dialogs overlaying the application"""
    window = curses.newpad(100, 100)
    padview = tui.PadView(window)
    drawstate = tui.WindowDrawState(window)
    stdwin.add_child(drawstate, padview)
    return tui.TextWindow(
            stdwin,
            event_handler,
            drawstate,
            padview)

def titlebar(stdwin: tui.MainWindow, event_handler: EventHandler):
    """Object for drawing the application titlebar"""
    window = curses.newwin(1, curses.COLS, 0, 0)
    drawstate = tui.WindowDrawState(window)

    def on_draw(win: curses.window) -> bool:
        win.erase()
        _, maxx = win.getmaxyx()
        text = "Minesweeper"[:maxx - 1]
        win.addstr(0, (maxx - len(text)) // 2, text)
        return True

    drawstate.on_draw = on_draw
    stdwin.add_child(drawstate)
    return tui.TextWindow(
            stdwin,
            event_handler,
            drawstate)

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=indent foldnestmax=2 foldlevel=2
