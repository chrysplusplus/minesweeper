#!/usr/bin/env python3

"""Main module for Minesweeper TUI game

Author: chrysplusplus

TODO

- [X] Debug updates after any key press
- [ ] Implement game logic
"""

import curses

from collections.abc import Callable, Iterable
from dataclasses import dataclass, KW_ONLY
from enum import Flag, auto
from functools import partial
from itertools import repeat
from random import shuffle
from typing import Any

import tui
from tui import L_ew, L_ns, L_nes, L_nsw, L_esw, L_new, L_nesw, C_es, C_sw, C_nw, C_ne
from util import clamp, same, label_tuple, compose2

@dataclass(slots = True)
class QuitEvent(tui.BaseEvent):
    """Event class for quitting the program"""
    ...

@dataclass(slots = True)
class MovementEvent(tui.BaseEvent):
    """Event class for movement keys"""
    _: KW_ONLY
    x: int = 0
    y: int = 0
    relative: bool = True

    def get_moved_coords_from(self, from_coords: tuple[int, int]) -> tuple[int, int]:# {{{
        """Return the new coords after movement from initial coords"""
        fromx, fromy = from_coords
        if self.relative:
            return (fromx + self.x, fromy + self.y)
        return (self.x, self.y) # }}}

@dataclass(slots = True)
class SelectEvent(tui.BaseEvent):
    """Event class for activating the current selection"""
    ...

@dataclass(slots = True)
class PlaceFlagEvent(tui.BaseEvent):
    """Event class for placing flags at the current selection"""
    ...

class Tile(Flag):
    """Flag Enumeration of grid tiles"""
    EMPTY = auto()
    MINE  = auto()
    FLAG  = auto()
    SEEN  = auto()

class TileGrid:
    """Class representing grid of tiles"""
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
        """Size of the grid, read-only"""
        return self._grid_size # }}}

    @property
    def mines(self):# {{{
        """Number of mines in the grid, read-only"""
        return self._mines # }}}

    def get_tile(self, coord: tuple[int, int]) -> Tile:# {{{
        """Get tile at coordinate"""
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        return self._grid[y * width + x] # }}}

    def set_tile(self, coord: tuple[int, int], tile: Tile):# {{{
        """Set tile at coordinate"""
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        self._grid[y * width + x] = tile # }}}

    def get_maybe_tile(self, coord: tuple[int, int]) -> Tile | None:# {{{
        """Get tile at coordinate if one exists there"""
        width, height = self._grid_size
        x, y = coord
        return self._grid[y * width + x] \
                if width > x >= 0 and height > y >= 0 \
                else None# }}}

class DebugPanel:
    """Debug window that can override MainWindow on_post_key to update on every
    keypress"""
    __slots__ = ("stdwin", "window", "padview", "drawstate", "is_visible", "update_callback",
                 "track_map")

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
        """Callback for drawing the window"""
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
        """Callback when enabled for updating after each keypress"""
        if self.update_callback is not None:
            self.update_callback()

        tui.windraw_refresh(self.drawstate, self.padview)
        self.stdwin.move_cursor(self.stdwin.stdcurs)# }}}

    def track(self, key: str, value: Any):# {{{
        """Add value or callable to map of tracked values"""
        self.track_map[key] = value# }}}

    def untrack(self, key: str) -> Any:# {{{
        """Remove and return tracked value"""
        return self.track_map.pop(key) if key in self.track_map else None# }}}

    def enable(self):# {{{
        """Enable the debug display"""
        self.update_callback = self.stdwin.on_post_key
        self.stdwin.on_post_key = self.on_update
        self.is_visible = True
        self.stdwin.refresh()# }}}

    def disable(self):# {{{
        """Disable the debug display"""
        self.stdwin.on_post_key = self.update_callback
        self.update_callback = None
        self.is_visible = False
        self.stdwin.refresh()# }}}

    def toggle(self):# {{{
        """Toggle the state of the debug display"""
        if self.is_visible:
            self.disable()
        else:
            self.enable()# }}}

class GameView:
    """Class for drawing the Minesweeper grid and handling game logic"""
    __slots__ = ("stdwin", "event_handler", "selection", "grid", "window", "padview", "drawstate")

    def __init__(self, stdwin: tui.MainWindow, event_handler: tui.EventHandler):# {{{
        self.stdwin = stdwin
        self.event_handler = event_handler

        self.selection = (0, 0)
        # TODO implement opening mercy (no mines around the first tile selected)
        self.grid = generate_grid((10, 10), 30)

        self.window = curses.newpad(100, 100)
        self.padview = tui.PadView(self.window, desired_screen_start = (2, 0))
        self.drawstate = tui.WindowDrawState(self.window)
        self.drawstate.on_draw = self.on_draw
        self.stdwin.add_child(self.drawstate, self.padview)# }}}

    def on_draw(self, win: curses.window) -> bool:# {{{
        """Callback for drawing"""
        win.erase()
        grid_size = self.grid.grid_size
        width, height = grid_size
        tui.win_addlines(win, gridlines(grid_size))

        for coords, _ in self.grid:
            symbol = get_symbol_for_coord_from(self.grid, coords)
            if symbol is not None:
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol)

        return True# }}}

    def on_grid_selection_changed(self, e: MovementEvent):# {{{
        """Callback for updating grid selection"""
        stdwin = self.stdwin
        self.selection = wrap_coords_to_grid(
                e.get_moved_coords_from(self.selection), self.grid.grid_size)
        stdwin.stdcurs = get_grid_view_screen_cursor(self.padview, self.selection)
        stdwin.move_cursor(stdwin.stdcurs)# }}}

    def on_select(self, _):
        """Callback for activating current selection"""
        tile = self.grid.get_tile(self.selection)
        if Tile.SEEN in tile:
            return
        if Tile.FLAG in tile:
            return

        tile ^= Tile.SEEN
        self.grid.set_tile(self.selection, tile)
        self.update_tile_display(self.selection)

    def on_flag(self, _):# {{{
        """Callback for toggling flag at the current grid selection"""
        tile = self.grid.get_tile(self.selection)
        if Tile.SEEN in tile:
            return

        tile ^= Tile.FLAG
        self.grid.set_tile(self.selection, tile)
        self.update_tile_display(self.selection)# }}}

    def bind_events(self):# {{{
        """Bind game events"""
        self.event_handler.bind(MovementEvent, self.on_grid_selection_changed)
        self.event_handler.bind(SelectEvent, self.on_select)
        self.event_handler.bind(PlaceFlagEvent, self.on_flag)# }}}

    def resize(self):# {{{
        """Resize the window view to fill the available space"""
        height, width = scale_grid_coords_to_screen_offset(self.grid.grid_size)
        width = width - 1
        width = clamp(width, curses.COLS - 3)
        height = clamp(height, curses.LINES - 4)
        starty = 2
        startx = (curses.COLS - width) // 2
        self.padview.desired_screen_start = (starty, startx)
        self.padview.desired_view_size = (height, width)# }}}

    def focus_cursor(self):# {{{
        """Focus screen cursor to grid selection"""
        # TODO check if gameview has focus
        stdwin = self.stdwin
        stdwin.stdcurs = get_grid_view_screen_cursor(self.padview, self.selection)
        stdwin.move_cursor(stdwin.stdcurs)# }}}

    def update_tile_display(self, coords: tuple[int, int]):# {{{
        """Update the specified grid coordinate in the window"""
        w, h = self.grid.grid_size
        x, y = coords
        assert 0 <= x < w and 0 <= y < h
        symbol = get_symbol_for_coord_from(self.grid, coords)
        symbol = ' ' if symbol is None else symbol
        self.window.addch(*scale_grid_coords_to_screen_offset(coords), symbol)
        self.window.refresh(*tui.padview_clamp(self.padview))
        self.stdwin.move_cursor(self.stdwin.stdcurs)# }}}

    def map_game_controls(self):# {{{
        """Map keys for game controls"""
        stdwin = self.stdwin
        event_handler = self.event_handler
        stdwin.add_mapping(tui.askey(" "), partial(event_handler.enqueue, SelectEvent()))
        stdwin.add_mapping(tui.askey("f"), partial(event_handler.enqueue, PlaceFlagEvent()))# }}}

@dataclass(slots = True)
class TextWindow:
    """Simple text window"""
    stdwin: tui.MainWindow
    event_handler: tui.EventHandler
    window: curses.window
    drawstate: tui.WindowDrawState
    padview: tui.PadView | None = None

class MinesweeperApp:
    """Main application class for marshalling initialisation and program state"""
    __slots__ = ("stdwin", "event_handler", "gameview", "keyhelp", "overlay", "titlebar",
                 "debug_panel")

    def __init__(self, stdwin: tui.MainWindow):# {{{
        self.stdwin = stdwin
        self.event_handler = tui.EventHandler()
        self.stdwin.on_post_key = self.event_handler.process

        self.gameview = GameView(self.stdwin, self.event_handler)
        self.keyhelp = key_instruction_bar(self.stdwin, self.event_handler)
        self.overlay = overlay(self.stdwin, self.event_handler)
        self.titlebar = titlebar(self.stdwin, self.event_handler)
        self.debug_panel = DebugPanel(self.stdwin)
        self.track_values()

        self.stdwin.stdcurs.cursor = (-1, -1)
        self.gameview.resize()
        self.gameview.focus_cursor()
        self.stdwin.refresh()

        self.map_window()
        self.map_selection()
        self.gameview.bind_events()
        self.gameview.map_game_controls()
        self.stdwin.mainloop() # }}}

    def on_resize(self):# {{{
        """Callback for window resizing"""
        curses.update_lines_cols()
        self.gameview.resize()
        self.gameview.focus_cursor()
        self.stdwin.refresh()# }}}

    def on_reset(self):# {{{
        """Callback for window reset/refresh"""
        self.stdwin.stdscr.clear()
        self.stdwin.refresh()# }}}

    # NOTE causes issue with resizing after breakpoint is triggered
    # likely due to switching modes without them being correctly set up
    def on_breakpoint(self):# {{{
        """Callback for debug breakpoint"""
        self.stdwin.stdscr.move(0, 0)
        self.stdwin.stdscr.clrtobot()
        self.stdwin.stdscr.refresh()
        curses.reset_shell_mode()
        breakpoint()
        curses.reset_prog_mode()
        self.stdwin.stdscr.clear()
        self.stdwin.refresh()# }}}

    def on_quit(self, _):# {{{
        """Callback for quitting mainloop"""
        self.stdwin.quit()# }}}

    def map_window(self): #{{{
        """Map the application keys for controlling the window state, such as
        screen refreshing, debug capabilities and quitting"""

        self.stdwin.add_mapping(tui.askey("KEY_RESIZE"), self.on_resize)
        self.stdwin.add_mapping(tui.askey("C-L"), self.on_reset)
        self.stdwin.add_mapping(tui.askey("g"), self.debug_panel.toggle)
        self.stdwin.add_mapping(tui.askey("b"), self.on_breakpoint)

        self.event_handler.bind(QuitEvent, self.on_quit)
        on_quit = partial(self.event_handler.enqueue, QuitEvent())
        self.stdwin.add_mapping(tui.askey("C-C"), on_quit)
        self.stdwin.add_mapping(tui.askey("q"), on_quit) # }}}

    def map_selection(self):# {{{
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
                           partial(event_handler.enqueue, SelectEvent()))# }}}

    def track_values(self):# {{{
        """Initialise the debug panel with tracked values"""
        self.debug_panel.track("cursor", lambda: self.stdwin.stdcurs)
        self.debug_panel.track("grid_coord", compose2(
            partial(getattr, self.gameview, "selection"), label_xycoords))
        self.debug_panel.track("pv_pad", compose2(
            partial(getattr, self.gameview.padview, "pad_start"), label_yxcoords))
        self.debug_panel.track("pv_screen", compose2(
            partial(getattr, self.gameview.padview, "desired_screen_start"), label_yxcoords))
        self.debug_panel.track("pv_view", compose2(
            partial(getattr, self.gameview.padview, "desired_view_size"), label_yxcoords)) # }}}

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
    """Initialise the curses library"""
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

def empty_tile_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:# {{{
    """Create an empty grid"""
    return TileGrid([], grid_size, mines) # }}}

def generate_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:# {{{
    """Generate a grid of specified size with specified amount of mines"""
    height, width = grid_size
    locations = [(x, y) for x in range(width) for y in range(height)]
    shuffle(locations)

    grid = [Tile.EMPTY for _ in range(width) for _ in range(height)]
    for minex,miney in locations[:mines]:
        grid[miney * width + minex] = Tile.MINE

    return TileGrid(grid, grid_size, mines) # }}}

def gridlines(grid_size: tuple[int, int]) -> list[str]:# {{{
    """Return a list of strings corresponding to the text lines representing a
    grid of a specified size"""
    width, height = grid_size
    line_format = "{outer_left}" + "{separator}".join(repeat("{tile}" * 3, width))\
            + "{outer_right}"

    line_top = line_format.format(
            outer_left = C_es, separator = L_esw, tile = L_ew, outer_right = C_sw)
    line_mid = line_format.format(
            outer_left = L_nes, separator = L_nesw, tile = L_ew, outer_right = L_nsw)
    line_bot = line_format.format(
            outer_left = C_ne, separator = L_new, tile = L_ew, outer_right = C_nw)
    line_tile = line_format.format(
            outer_left = L_ns, separator = L_ns, tile = " ", outer_right = L_ns)

    lines = [line_top]
    for y in range(height):
        lines.append(line_tile)
        if y < height - 1:
            lines.append(line_mid)
    lines.append(line_bot)
    return lines # }}}

def label_yxcoords(coords: tuple[int, int]) -> str:# {{{
    """Format a string with coordinates in y-x order"""
    return label_tuple(coords, "y", "x") # }}}

def label_xycoords(coords: tuple[int, int]) -> str:# {{{
    """Format a string with coordinates in x-y order"""
    return label_tuple(coords, "x", "y") # }}}

def iter_grid_neighbours(grid: TileGrid, coords: tuple[int, int]) -> Iterable[Tile]:# {{{
    """Return an iterator of neighbouring tiles to specfied grid coordinates"""
    thisx, thisy = coords
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            if y == 0 and x == 0:
                continue
            neighbour = grid.get_maybe_tile((thisx + x, thisy + y))
            if neighbour is None:
                continue
            yield neighbour# }}}

def get_symbol_for_coord_from(grid: TileGrid, coords: tuple[int, int]) -> str | None:# {{{
    """Determine display symbol for grid coordinates"""
    tile = grid.get_tile(coords)
    symbol: str | None = None
    if Tile.FLAG in tile:
        symbol = 'f'
    elif Tile.SEEN not in tile:
        symbol = None
    elif Tile.MINE in tile:
        symbol = 'x'
    else:
        n_neighbouring_mines = sum(1 if Tile.MINE in t else 0
                                   for t in iter_grid_neighbours(grid, coords))
        symbol = '□' if n_neighbouring_mines == 0 else str(n_neighbouring_mines)

    return symbol# }}}

def wrap_coords_to_grid(# {{{
        coords: tuple[int, int], grid_size: tuple[int, int]) -> tuple[int, int]:
    """Calculate coordinates wrapped inside a grid"""
    x, y = coords
    w, h = grid_size
    return (x % w, y % h) # }}}

def scale_grid_coords_to_screen_offset(grid_coords: tuple[int, int]) -> tuple[int, int]:# {{{
    """Scale grid coordinates to offset from the origin of the grid window"""
    x, y = grid_coords
    return (2 * y + 1, 4 * x + 2)# }}}

def get_grid_view_screen_cursor(# {{{
        grid_view: tui.PadView, selection_coords: tuple[int, int]) -> tui.Cursor:
    """Calculate screen coordinates for a given coordinate in a grid"""
    y, x = scale_grid_coords_to_screen_offset(selection_coords)
    starty, startx = grid_view.desired_screen_start
    pady, padx = grid_view.pad_start
    return tui.Cursor((starty - pady + y, startx - padx + x))# }}}

def key_instruction_bar(stdwin: tui.MainWindow, event_handler: tui.EventHandler) -> TextWindow:# {{{
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
    return TextWindow(
            stdwin,
            event_handler,
            window,
            drawstate)# }}}

def overlay(stdwin: tui.MainWindow, event_handler: tui.EventHandler):# {{{
    """Object for drawing dialogs overlaying the application"""
    window = curses.newpad(100, 100)
    padview = tui.PadView(window)
    drawstate = tui.WindowDrawState(window)
    stdwin.add_child(drawstate, padview)
    return TextWindow(
            stdwin,
            event_handler,
            window,
            drawstate,
            padview)# }}}

def titlebar(stdwin: tui.MainWindow, event_handler: tui.EventHandler):# {{{
    """Object for drawing the application titlebar"""
    window = curses.newwin(1, curses.COLS, 0, 0)
    drawstate = tui.WindowDrawState(window)

    def on_draw(win: curses.window) -> bool:
        win.erase()
        _, maxx = win.getmaxyx()
        text = "Minesweeper"[:maxx + 1]
        win.addstr(0, (maxx - len(text)) // 2, text)
        return True

    drawstate.on_draw = on_draw
    stdwin.add_child(drawstate)
    return TextWindow(
            stdwin,
            event_handler,
            window,
            drawstate)# }}}

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=marker
