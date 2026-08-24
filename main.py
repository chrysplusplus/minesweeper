#!/usr/bin/env python3

"""
TODO

- [X] Debug updates after any key press
- [ ] Implement game logic
"""

import curses

from dataclasses import dataclass, KW_ONLY
from enum import Flag, auto
from functools import partial
from itertools import repeat
from typing import Any

import tui
from util import clamp, same, label_tuple, compose2

class QuitEvent(tui.BaseEvent):
    pass

@dataclass
class MovementEvent(tui.BaseEvent):
    _: KW_ONLY
    x: int = 0
    y: int = 0
    relative: bool = True

    def get_moved_coords_from(self, from_coords: tuple[int, int]) -> tuple[int, int]:# {{{
        fromx, fromy = from_coords
        if self.relative:
            return (fromx + self.x, fromy + self.y)
        else:
            return (self.x, self.y) # }}}

class Tile(Flag):
    EMPTY = auto()
    MINE  = auto()
    FLAG  = auto()
    SEEN  = auto()

class TileGrid:
    __slots__ = ("_grid", "_grid_size", "_mines")

    def __init__(self, grid: list[Tile], grid_size: tuple[int, int], mines: int):# {{{
        self._grid: list[Tile] = grid
        self._grid_size = grid_size
        self._mines = mines # }}}

    def __iter__(self):# {{{
        for i, tile in enumerate(self._grid):
            yield (divmod(i, self._grid_size[0]), tile) # }}}

    @property
    def grid_size(self):# {{{
        return self._grid_size # }}}

    @property
    def mines(self):# {{{
        return self._mines # }}}

    def get_tile(self, coord) -> Tile:# {{{
        width, height = self._grid_size
        x, y = coord
        assert x >= 0 and x < width and y >= 0 and y < height
        return self._grid[y * width + x] # }}}

    def set_tile(self, coord: int, tile: Tile):# {{{
        width, height = self._grid_size
        x, y = coord
        assert x >= 0 and x < width and y >= 0 and y < height
        self._grid[y * width + x] = tile # }}}


def empty_tile_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:# {{{
    return TileGrid([], grid_size, mines) # }}}

class DebugPanel:
    def __init__(self, stdwin: tui.MainWindow):# {{{
        self.stdwin = stdwin
        self.window = curses.newpad(100, 100)
        self.padview = tui.PadView(self.window)
        self.drawstate = tui.WindowDrawState(self.window)
        self.drawstate.on_draw = self.on_draw
        self.stdwin.add_child(self.drawstate, self.padview)

        self.is_visible = False
        self.update_callback: Callable[[], None] | None = None
        self.track_map = {} # }}}

    def on_draw(self, win: curses.window) -> bool:# {{{
        pv = self.padview
        assert same(pv.pad, win)
        win.erase()
        if not self.is_visible:
            pv.desired_view_size = (0, 0)
            return True

        maxy, maxx = win.getmaxyx()
        maxx = min(maxx, curses.COLS - 1)
        win.addstr(0, 0, "Debug", ATTR_WHITE)
        y = 1
        w = 6
        for key, value in self.track_map.items():
            value = value() if callable(value) else value
            line = f"{key}: {value}"[:maxx]
            w = max(w, len(line))
            win.addstr(y, 0, line, ATTR_WHITE)
            y += 1
            if y == maxy:
                break

        pv.desired_view_size = (y, w)
        return True# }}}

    def on_update(self):# {{{
        if self.update_callback is not None: self.update_callback()
        tui.windraw_refresh(self.drawstate, self.padview)# }}}

    def track(self, key: str, value: Any):# {{{
        self.track_map[key] = value# }}}

    def untrack(self, key: str) -> Any:# {{{
        return self.track_map.pop(key) if key in self.track_map else None# }}}

    def enable(self):# {{{
        self.update_callback = self.stdwin.on_post_key
        self.stdwin.on_post_key = self.on_update
        self.is_visible = True
        self.stdwin.refresh()# }}}

    def disable(self):# {{{
        self.stdwin.on_post_key = self.update_callback
        self.update_callback = None
        self.is_visible = False
        self.stdwin.refresh()# }}}

    def toggle(self):# {{{
        if self.is_visible:
            self.disable()
        else:
            self.enable()# }}}

class MinesweeperApp:
    def __init__(self, stdwin: tui.MainWindow):# {{{
        self.stdwin = stdwin
        self.grid = empty_tile_grid((10, 10), 30)
        self.selection = (0, 0)

        self.event_handler = tui.EventHandler()
        self.stdwin.on_post_key = self.event_handler.process

        self.init_gameview()
        self.init_keyhelp()
        self.init_overlay()
        self.init_titlebar()
        self.init_debug()

        self.stdwin.stdcurs.cursor = (-1, -1)
        self.resize_gameview()
        self.stdwin.refresh()

        self.map_window()
        self.map_selection()
        self.stdwin.mainloop() # }}}

    def init_gameview(self):# {{{
        self.game_win = curses.newpad(100, 100)
        self.game_vw = tui.PadView(self.game_win, desired_screen_start = (2, 0))
        self.game = tui.WindowDrawState(self.game_win)
        self.game.on_draw = self.on_game_draw
        self.stdwin.add_child(self.game, self.game_vw)

        self.event_handler.bind(MovementEvent, self.on_grid_selection_changed) # }}}

    def init_overlay(self):# {{{
        self.overlay_win = curses.newpad(100, 100)
        self.overlay_vw = tui.PadView(self.overlay_win)
        self.overlay = tui.WindowDrawState(self.overlay_win)
        self.stdwin.add_child(self.overlay, self.overlay_vw) # }}}

    def init_keyhelp(self):# {{{
        self.keyhelp_win = curses.newwin(1, curses.COLS, curses.LINES - 1, 0)
        self.keyhelp = tui.WindowDrawState(self.keyhelp_win)
        self.keyhelp.on_draw = self.on_keyhelp_draw
        self.stdwin.add_child(self.keyhelp) # }}}

    def init_titlebar(self):# {{{
        self.titlebar_win = curses.newwin(1, curses.COLS, 0, 0)
        self.titlebar = tui.WindowDrawState(self.titlebar_win)
        self.titlebar.on_draw = self.on_titlebar_draw
        self.stdwin.add_child(self.titlebar) # }}}

    def init_debug(self):# {{{
        self.debug_panel = DebugPanel(self.stdwin)
        self.debug_panel.track("cursor", lambda: self.stdwin.stdcurs)
        self.debug_panel.track("grid_coord", compose2(partial(getattr, self, "selection"), label_xycoords))
        self.debug_panel.track("pv_pad", compose2(partial(getattr, self.game_vw, "pad_start"), label_yxcoords))
        self.debug_panel.track("pv_screen", compose2(partial(getattr, self.game_vw, "desired_screen_start"), label_yxcoords))
        self.debug_panel.track("pv_view", compose2(partial(getattr, self.game_vw, "desired_view_size"), label_yxcoords)) # }}}

    def on_game_draw(self, win: curses.window) -> bool:# {{{
        win.erase()

        grid_size = self.grid.grid_size
        width, height = grid_size
        tui.win_addlines(win, gridlines(grid_size))

        for (x, y), tile in self.grid:
            if Tile.MINE in tile:
                win.addch(2 * y + 1, 4 * x + 2, 'X')

        return True # }}}

    def on_keyhelp_draw(self, win: curses.window) -> bool:# {{{
        win.mvwin(curses.LINES - 1, 0)
        _, maxx = win.getmaxyx()
        win.erase()
        text = "KEYS: ←↑↓→/wasd to move; f to place flag; Space/Return to check; q/^C to quit"[:maxx - 1]
        win.addstr(0, 0, text)
        return True # }}}

    def on_titlebar_draw(self, win: curses.window) -> bool:# {{{
        win.erase()
        _, maxx = win.getmaxyx()
        text = "Minesweeper"[:maxx + 1]
        win.addstr(0, (maxx - len(text)) // 2, text)
        return True # }}}

    def on_grid_selection_changed(self, e: MovementEvent):# {{{
        stdwin = self.stdwin
        self.selection = wrap_coords_to_grid(
                e.get_moved_coords_from(self.selection), self.grid.grid_size)
        stdwin.stdcurs = get_grid_view_screen_cursor(self.game_vw, self.selection)
        stdwin.move_cursor(stdwin.stdcurs) # }}}

    # TODO refactor callbacks
    def map_window(self): #{{{
        def on_resize():
            curses.update_lines_cols()
            self.resize_gameview()
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("KEY_RESIZE"), on_resize)

        def on_reset():
            self.stdwin.stdscr.clear()
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("C-L"), on_reset)

        self.stdwin.add_mapping(tui.askey("g"), self.debug_panel.toggle)

        def on_breakpoint():
            self.stdwin.stdscr.move(0, 0)
            self.stdwin.stdscr.clrtobot()
            self.stdwin.stdscr.refresh()
            curses.reset_shell_mode()
            breakpoint()
            curses.reset_prog_mode()
            self.stdwin.stdscr.clear()
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("b"), on_breakpoint)

        self.event_handler.bind(QuitEvent, lambda _: self.stdwin.quit())
        on_quit = lambda: self.event_handler.enqueue(QuitEvent())
        self.stdwin.add_mapping(tui.askey("C-C"), on_quit)
        self.stdwin.add_mapping(tui.askey("q"), on_quit) # }}}

    def map_selection(self):# {{{
        stdwin = self.stdwin
        event_handler = self.event_handler
        stdwin.add_mapping(tui.askey("k"),
                           partial(event_handler.enqueue, MovementEvent(y = -1)))
        stdwin.add_mapping(tui.askey("j"),
                           partial(event_handler.enqueue, MovementEvent(y = 1)))
        stdwin.add_mapping(tui.askey("h"),
                           partial(event_handler.enqueue, MovementEvent(x = -1)))
        stdwin.add_mapping(tui.askey("l"),
                           partial(event_handler.enqueue, MovementEvent(x = 1))) # }}}

    def resize_gameview(self):# {{{
        pv = self.game_vw
        grid_size = self.grid.grid_size
        grid_width, grid_height = grid_size
        width = clamp(grid_width * 4 + 1, curses.COLS - 3)
        height = clamp(grid_height * 2 + 1, curses.LINES - 4)
        starty = 2
        startx = (curses.COLS - width) // 2
        pv.desired_screen_start = (starty, startx)
        pv.desired_view_size = (height, width)

        # TODO check if gameview has focus
        stdwin = self.stdwin
        stdwin.stdcurs = get_grid_view_screen_cursor(self.game_vw, self.selection)
        stdwin.move_cursor(stdwin.stdcurs) # }}}

def wrap_coords_to_grid(coords: tuple[int, int], grid_size: tuple[int, int]) -> tuple[int, int]:# {{{
    x, y = coords
    w, h = grid_size
    return (x % w, y % h) # }}}

def get_grid_view_screen_cursor(grid_view: tui.PadView, selection_coords: tuple[int, int]) -> tui.Cursor:# {{{
    x, y = selection_coords
    starty, startx = grid_view.desired_screen_start
    pady, padx = grid_view.pad_start
    return tui.Cursor((starty - pady + 2 * y + 1, startx - padx + 4 * x + 2)) }}}

ATTR_NORMAL = curses.A_NORMAL
ATTR_UNDER  = curses.A_UNDERLINE

ATTR_BLUE:      int # initialised by init_curses
ATTR_CYAN:      int # initialised by init_curses
ATTR_GREEN:     int # initialised by init_curses
ATTR_MAGENTA:   int # initialised by init_curses
ATTR_RED:       int # initialised by init_curses
ATTR_WHITE:     int # initialised by init_curses
ATTR_YELLOW:    int # initialised by init_curses

def init_curses(stdscr: curses.window):# {{{
    curses.raw()
    curses.use_default_colors()

    # init colors
    assert curses.COLOR_PAIRS > 8
    curses.init_pair(1, curses.COLOR_BLUE, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_GREEN, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_RED, -1)
    curses.init_pair(6, curses.COLOR_WHITE, -1)
    curses.init_pair(7, curses.COLOR_YELLOW, -1)

    global ATTR_BLUE, ATTR_CYAN, ATTR_GREEN, ATTR_MAGENTA, ATTR_RED, ATTR_WHITE, ATTR_YELLOW
    ATTR_BLUE     = curses.color_pair(1)
    ATTR_CYAN     = curses.color_pair(2)
    ATTR_GREEN    = curses.color_pair(3)
    ATTR_MAGENTA  = curses.color_pair(4)
    ATTR_RED      = curses.color_pair(5)
    ATTR_WHITE    = curses.color_pair(6)
    ATTR_YELLOW   = curses.color_pair(7) # }}}

def generate_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:# {{{
    height, width = grid_size
    locations = [(x, y) for x in range(width) for y in range(height)]

    from random import shuffle
    shuffle(locations)

    grid = [Tile.EMPTY for _ in range(width) for _ in range(height)]
    for minex,miney in locations[:mines]:
        grid[miney * width + minex] = Tile.MINE

    return TileGrid(grid, grid_size, mines) # }}}

def gridlines(grid_size: tuple[int, int]) -> list[str]:# {{{
    width, height = grid_size
    line_format = "{outer_left}" + "{separator}".join(repeat("{tile}" * 3, width)) + "{outer_right}"

    from tui import L_ew, L_ns, L_nes, L_nsw, L_esw, L_new, L_nesw, C_es, C_sw, C_nw, C_ne
    line_top = line_format.format(outer_left = C_es, separator = L_esw, tile = L_ew, outer_right = C_sw)
    line_mid = line_format.format(outer_left = L_nes, separator = L_nesw, tile = L_ew, outer_right = L_nsw)
    line_bot = line_format.format(outer_left = C_ne, separator = L_new, tile = L_ew, outer_right = C_nw)
    line_tile = line_format.format(outer_left = L_ns, separator = L_ns, tile = " ", outer_right = L_ns)

    lines = [line_top]
    for y in range(height):
        lines.append(line_tile)
        if y < height - 1:
            lines.append(line_mid)
    lines.append(line_bot)
    return lines # }}}

def label_yxcoords(coords: tuple[int, int]) -> str:# {{{
    return label_tuple(coords, "y", "x") # }}}

def label_xycoords(coords: tuple[int, int]) -> str:# {{{
    return label_tuple(coords, "x", "y") # }}}

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=marker
