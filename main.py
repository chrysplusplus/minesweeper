#!/usr/bin/env python3

import curses

from enum import Enum, auto
from itertools import repeat

import tui
from util import clamp

class BaseEvent:
    pass

class QuitEvent(BaseEvent):
    pass

class Tile(Enum):
    EMPTY = auto()
    MINE  = auto()
    FLAG  = auto()

class TileGrid(list):
    def __init__(self, grid_size: tuple[int, int], mines: int, *args, **kwargs):# {{{
        self._grid_size = grid_size
        self._mines = mines
        super().__init__(*args, **kwargs)
# }}}
    @property
    def grid_size(self):# {{{
        return self._grid_size
# }}}
    @property
    def mines(self):# {{{
        return self._mines
# }}}

class MinesweeperApp:
    def __init__(self, stdwin: tui.MainWindow):# {{{
        self.stdwin = stdwin
        self.grid = generate_grid((10, 10), 30)

        # TODO
        #self.event_queue: list[BaseEvent] = []
        #self.stdwin.on_post_key = self.on_post_key

        # TODO
        self.init_gameview()
        self.init_keyhelp()
        self.init_overlay()
        self.init_titlebar()
        #self.init_statusbar()
        self.init_debug()

        self.resize_gameview()
        self.stdwin.stdcurs.cursor = (-1, -1)
        self.stdwin.refresh()

        self.map_window()
        self.stdwin.mainloop()
# }}}
    def init_gameview(self):# {{{
        self.game_win = curses.newpad(100, 100)
        self.game_vw = tui.PadView(self.game_win, (0, 0), (2, 0), (0, 0))
        self.game = tui.WindowDrawState(self.game_win)
        self.game.on_draw = self.on_game_draw
        self.stdwin.add_child(self.game, self.game_vw)
# }}}
    def init_overlay(self):# {{{
        self.overlay_win = curses.newpad(100, 100)
        self.overlay_vw = tui.PadView(self.overlay_win, (0, 0), (0, 0), (0, 0))
        self.overlay = tui.WindowDrawState(self.overlay_win)
        self.stdwin.add_child(self.overlay, self.overlay_vw)
# }}}
    def init_keyhelp(self):# {{{
        self.keyhelp_win = curses.newwin(1, curses.COLS, curses.LINES - 2, 0)
        self.keyhelp = tui.WindowDrawState(self.keyhelp_win)
        self.keyhelp.on_draw = self.on_keyhelp_draw
        self.stdwin.add_child(self.keyhelp)
# }}}
    def init_titlebar(self):# {{{
        self.titlebar_win = curses.newwin(1, curses.COLS, 0, 0)
        self.titlebar = tui.WindowDrawState(self.titlebar_win)
        self.titlebar.on_draw = self.on_titlebar_draw
        self.stdwin.add_child(self.titlebar)
    # }}}
    def init_debug(self):# {{{
        self.debug_win = curses.newpad(100, 100)
        self.debug_vw = tui.PadView(self.debug_win, (0, 0), (0, 0), (0, 0))
        self.debug_scr = tui.WindowDrawState(self.debug_win)
        self.debug_scr.on_draw = self.on_debug_draw
        self.stdwin.add_child(self.debug_scr, self.debug_vw)

        self.debug_show = False
        self.debug_vals = {}
# }}}

    def on_game_draw(self, win: curses.window) -> bool:# {{{
        win.erase()

        grid_size = self.grid.grid_size
        width, height = grid_size
        tui.win_addlines(win, gridlines(grid_size))

        return True
# }}}
    def on_keyhelp_draw(self, win: curses.window) -> bool:# {{{
        win.erase()
        _, maxx = win.getmaxyx()
        text = "KEYS: ←↑↓→ or wasd to move; f to place flag; Space or Return to clear"[:maxx + 1]
        win.addstr(0, 0, text)
        return True
# }}}
    def on_titlebar_draw(self, win: curses.window) -> bool:# {{{
        win.erase()
        _, maxx = win.getmaxyx()
        text = "Minesweeper"[:maxx + 1]
        win.addstr(0, (maxx - len(text)) // 2, text)
        return True
# }}}
    def on_debug_draw(self, win: curses.window) -> bool:# {{{
        pv = self.debug_vw
        assert id(pv.pad) == id(win)
        win.erase()
        if self.debug_show:
            maxy, maxx = win.getmaxyx()
            maxx = min(maxx, curses.COLS - 1)
            assert maxy > 2
            win.addstr(0, 0, "Debug", ATTR_WHITE)
            y = 1
            w = 6
            for key, value in self.debug_vals.items():
                value = value() if callable(value) else value
                line = f"{key}: {value}"[:maxx]
                w = max(w, len(line))
                win.addstr(y, 0, line, ATTR_WHITE)
                y += 1
                if y == maxy:
                    break

            pv.desired_view_size = (y, w)

        else:
            pv.desired_view_size = (0, 0)

        return True
# }}}

    def map_window(self):# {{{
        def on_resize():
            curses.update_lines_cols()
            self.resize_gameview()
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("KEY_RESIZE"), on_resize)

        def on_reset():
            self.stdwin.stdscr.clear()
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("C-L"), on_reset)

        def on_debug_toggle():
            self.debug_show = not self.debug_show
            self.stdwin.refresh()

        self.stdwin.add_mapping(tui.askey("g"), on_debug_toggle)

        self.stdwin.add_mapping(tui.askey("C-C"), self.stdwin.quit)
# }}}

    def resize_gameview(self):# {{{
        pv = self.game_vw
        grid_size = self.grid.grid_size
        grid_width, grid_height = grid_size
        width = clamp(grid_width * 2 + 1, curses.COLS - 3)
        height = clamp(grid_height * 2 + 1, curses.LINES - 5)
        starty = 2
        startx = (curses.COLS - width) // 2
        pv.desired_screen_start = (starty, startx)
        pv.desired_view_size = (width, height)
# }}}

ATTR_NORMAL = curses.A_NORMAL
ATTR_UNDER = curses.A_UNDERLINE

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
    ATTR_YELLOW   = curses.color_pair(7)
# }}}
def generate_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:# {{{
    height, width = grid_size
    locations = [(x, y) for x in range(width) for y in range(height)]

    from random import shuffle
    shuffle(locations)

    grid = TileGrid(grid_size, mines, [Tile.EMPTY for _ in range(width) for _ in range(height)])
    for minex,miney in locations[:mines]:
        grid[miney * width + minex] = Tile.MINE

    return grid
# }}}
def gridlines(grid_size: tuple[int, int]) -> list[str]:# {{{
    width, height = grid_size
    line_format = "{outer_left}" + "{separator}".join(repeat("{tile}", width)) + "{outer_right}"

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
    return lines
# }}}

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=marker
