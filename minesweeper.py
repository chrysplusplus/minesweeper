#!/usr/bin/env python3

"""Main module for Minesweeper TUI game

Author: chrysplusplus

TODO

- [ ] Ensure game padview and screen are large enough for the grid
- [ ] Implement game logic
    - [X] Lose on revealing a mine
    - [X] Win on revealing last empty tile
    - [ ] Fix reveal display bugs
- [ ] Implement settings dialog
- [ ] Add styles for different tiles
"""

import curses

from collections.abc import Callable, Iterable
from dataclasses import dataclass, KW_ONLY
from enum import Flag, auto, Enum
from functools import partial
from itertools import repeat, pairwise
from random import shuffle
from typing import Any, Protocol

import tui
from util import clamp, same, label_tuple, compose2, transpose_2d

from boxsym import (
        L_ew, L_ns,
        L_es, L_sw, L_ne, L_nw,
        L_nes, L_nsw, L_esw, L_new,
        L_nesw,
        C_es, C_sw, C_nw, C_ne)

class DialogLike(Protocol):
    """Protocol defining requirements of a dialog-like type"""
    textwindow: tui.TextWindow# {{{

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing"""

    def bind_events(self):
        """Bind dialog events"""

    def unbind_events(self):
        """Unbind dialog events"""# }}}

@dataclass(slots = True)
class MovementEvent(tui.BaseEvent):
    """Event class for movement keys"""
    _: KW_ONLY
    x: int = 0
    y: int = 0
    relative: bool = True

    def get_moved_coords_from(self, from_coords: tuple[int, int]) -> tuple[int, int]:
        """Return the new coords after movement from initial coords"""# {{{
        fromx, fromy = from_coords
        if self.relative:
            return (fromx + self.x, fromy + self.y)
        return (self.x, self.y) # }}}

@dataclass(slots = True)
class SelectEvent(tui.BaseEvent):
    """Event class for activating the current selection"""

@dataclass(slots = True)
class PlaceFlagEvent(tui.BaseEvent):
    """Event class for placing flags at the current selection"""

@dataclass(slots = True)
class GameLoseEvent(tui.BaseEvent):
    """Event class for the user losing the game"""
    coords: tuple[int, int]

@dataclass(slots = True)
class GameWinEvent(tui.BaseEvent):
    """Event class for the user winning the game"""

@dataclass(slots = True)
class OpenDialogEvent(tui.BaseEvent):
    """Event class for opening a dialog"""
    dialog: DialogLike

@dataclass(slots = True)
class DialogRestoreEvent(tui.BaseEvent):
    """Event class for restoring from a dialog"""
    dialog: DialogLike

@dataclass(slots = True)
class QuitEvent(tui.BaseEvent):
    """Event class for the user quitting the program"""
    _: KW_ONLY
    confirm_dialog: DialogLike | None = None

class Tile(Flag):
    """Flag Enumeration of grid tiles"""
    EMPTY = auto()
    MINE  = auto()
    FLAG  = auto()
    SEEN  = auto()
    TRANS = auto()

class TileGrid:
    """Class representing grid of tiles"""
    __slots__ = ("_grid", "_grid_size", "_mines", "_flags")

    def __init__(self, grid: list[Tile], grid_size: tuple[int, int], mines: int):
        assert mines < (grid_size[0] * grid_size[1])# {{{
        self._grid: list[Tile] = grid
        self._grid_size = grid_size
        self._mines = mines
        self._flags = 0# }}}

    def __iter__(self) -> Iterable[tuple[tuple[int, int], Tile]]:
        width, _ = self._grid_size# {{{
        for i, tile in enumerate(self._grid):
            y, x = divmod(i, width)
            yield ((x, y), tile) # }}}

    @property
    def grid_size(self):
        """Size of the grid, read-only"""# {{{
        return self._grid_size # }}}

    @property
    def mines(self):
        """Number of mines remaining in the grid, read-only"""# {{{
        return self._mines - self._flags#}}}

    def get_tile(self, coord: tuple[int, int]) -> Tile:
        """Get tile at coordinate"""# {{{
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        return self._grid[y * width + x] # }}}

    def set_tile(self, coord: tuple[int, int], tile: Tile):
        """Set tile at coordinate"""# {{{
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        self._check_flag(coord, tile)
        self._grid[y * width + x] = tile # }}}

    def get_maybe_tile(self, coord: tuple[int, int]) -> Tile | None:
        """Get tile at coordinate if one exists there"""# {{{
        width, height = self._grid_size
        x, y = coord
        return self._grid[y * width + x] \
                if width > x >= 0 and height > y >= 0 \
                else None# }}}

    def empty(self) -> bool:
        """Return True if the grid is empty and unpopulated"""# {{{
        return len(self._grid) == 0# }}}

    def populate_except_for(self, *except_coords: tuple[int, int]):
        """Populate grid from grid_size and mines, avoiding specified coords"""# {{{
        width, height = self._grid_size
        locations = [(x, y) for x in range(width) for y in range(height)
                     if (x, y) not in except_coords]
        shuffle(locations)

        self._grid = [Tile.EMPTY for _ in range(width) for _ in range(height)]
        for minex, miney in locations[:self._mines]:
            self._grid[miney * width + minex] = Tile.MINE# }}}

    def _check_flag(self, coord: tuple[int, int], new_tile: Tile):
        """Determine whether changing tile affects the flag count"""# {{{
        x, y = coord
        width, _ = self._grid_size
        old_tile = self._grid[y * width + x]
        if Tile.FLAG in old_tile and Tile.FLAG not in new_tile:
            self._flags -= 1
        elif Tile.FLAG not in old_tile and Tile.FLAG in new_tile:
            self._flags += 1# }}}

class DebugPanel:
    """Debug window that can override MainWindow on_post_key to update on every
    keypress"""
    __slots__ = ("stdwin", "window", "padview", "drawstate", "is_visible", "update_callback",
                 "track_map")

    def __init__(self, stdwin: tui.MainWindow):
        self.stdwin = stdwin# {{{
        self.window = curses.newpad(100, 100)
        self.padview = tui.PadView(self.window)
        self.drawstate = tui.WindowDrawState(self.window)
        self.drawstate.on_draw = self.on_draw
        self.stdwin.add_child(self.drawstate, self.padview)

        self.is_visible = False
        self.update_callback: Callable[[], None] | None = None
        self.track_map = {} # }}}

    def on_draw(self, win: curses.window) -> bool:
        """Callback for drawing the window"""# {{{
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
            value_text = value() if callable(value) else value
            line = f"{key}: {value_text}"[:maxx]
            w = max(w, len(line))
            win.addstr(y, 0, line, ATTR_WHITE)
            y += 1
            if y == maxy:
                break

        pv.desired_view_size = (y, w)
        return True# }}}

    def on_update(self):
        """Callback when enabled for updating after each keypress"""# {{{
        if self.update_callback is not None:
            self.update_callback()

        tui.windraw_refresh(self.drawstate, self.padview)
        self.stdwin.move_cursor(self.stdwin.stdcurs)# }}}

    def track(self, key: str, value: Any):
        """Add value or callable to map of tracked values"""# {{{
        self.track_map[key] = value# }}}

    def untrack(self, key: str) -> Any:
        """Remove and return tracked value"""# {{{
        return self.track_map.pop(key) if key in self.track_map else None# }}}

    def enable(self):
        """Enable the debug display"""# {{{
        self.update_callback = self.stdwin.on_post_key
        self.stdwin.on_post_key = self.on_update
        self.is_visible = True
        self.stdwin.refresh()# }}}

    def disable(self):
        """Disable the debug display"""# {{{
        self.stdwin.on_post_key = self.update_callback
        self.update_callback = None
        self.is_visible = False
        self.stdwin.refresh()# }}}

    def toggle(self):
        """Toggle the state of the debug display"""# {{{
        if self.is_visible:
            self.disable()
        else:
            self.enable()# }}}

class GameState(Enum):
    """Enumeration of possible states for GameView"""
    INITIALISING = auto()
    PLAYING = auto()
    WIN = auto()
    LOSE = auto()

# TODO check these notes
# NOTE pylint gives R0904: Too many public methods
class GameView:
    """Class for drawing the Minesweeper grid and handling game logic"""
    __slots__ = ("textwindow", "selection", "state", "grid", "last_quit_callback")

    def __init__(self, stdwin: tui.MainWindow, event_handler: tui.EventHandler, grid: TileGrid):
        window = curses.newpad(100, 100)# {{{
        padview = tui.PadView(window, desired_screen_start = (2, 0))
        drawstate = tui.WindowDrawState(window)
        drawstate.on_draw = self.on_game_draw
        stdwin.add_child(drawstate, padview)

        self.textwindow = tui.TextWindow(stdwin, event_handler, drawstate, padview)
        self.selection = (0, 0)
        self.state = GameState.INITIALISING
        self.grid = grid
        # TODO dialog handling class
        self.last_quit_callback: Callable[[tui.BaseEvent], None] | None = None# }}}

    def on_game_draw(self, win: curses.window) -> bool:
        """Callback for drawing during normal gameplay"""# {{{
        win.erase()
        self.draw_grid(win)
        self.update_mine_counter(win)
        return True# }}}

    def on_lose_draw(self, win: curses.window, *, lose_coords: tuple[int, int]) -> bool:
        """Callback for drawing after losing the game"""# {{{
        win.erase()
        self.draw_grid(win, lose_coords = lose_coords)
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You lose!", ATTR_RED)
        return True# }}}

    def on_win_draw(self, win: curses.window) -> bool:
        """Callback for drawing after winning the game"""# {{{
        win.erase()
        self.draw_grid(win)
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You win!", ATTR_YELLOW)
        return True# }}}

    def on_grid_selection_changed(self, e: MovementEvent):
        """Callback for updating grid selection"""# {{{
        stdwin = self.textwindow.stdwin
        self.selection = wrap_coords_to_grid(
                e.get_moved_coords_from(self.selection), self.grid.grid_size)
        stdwin.stdcurs = get_grid_view_screen_cursor(self.textwindow.padview, self.selection)
        stdwin.move_cursor(stdwin.stdcurs)# }}}

    def on_select(self, _):
        """Callback for activating current selection"""# {{{
        if self.grid.empty():
            self.grid.populate_except_for(
                    *iter_3x3_area_coords(self.grid.grid_size, self.selection))

        self.reveal_tile_at(self.selection)
        tui.windraw_refresh(self.textwindow.drawstate, self.textwindow.padview)
        self.textwindow.stdwin.move_cursor(self.textwindow.stdwin.stdcurs)# }}}

    def on_flag(self, _):
        """Callback for toggling flag at the current grid selection"""# {{{
        if self.grid.empty():
            return

        tile = self.grid.get_tile(self.selection)
        if Tile.SEEN in tile:
            return

        tile ^= Tile.FLAG
        self.grid.set_tile(self.selection, tile)
        self.mark_tile_at(self.selection)
        self.update_mine_counter(self.textwindow.window)
        self.refresh()# }}}

    def on_lose(self, e: GameLoseEvent):
        """Callback for losing the game"""# {{{
        lose_coords = e.coords
        self.state = GameState.LOSE
        self.unbind_game_events()
        self.reveal_all_mines()
        self.textwindow.drawstate.on_draw = partial(self.on_lose_draw, lose_coords = lose_coords)
        tui.windraw_refresh(self.textwindow.drawstate, self.textwindow.padview)
        self.textwindow.stdwin.move_cursor(self.textwindow.stdwin.stdcurs)# }}}

    def on_win(self, _):
        """Callback for winning the game"""# {{{
        self.state = GameState.WIN
        self.unbind_game_events()
        self.textwindow.drawstate.on_draw = self.on_win_draw
        tui.windraw_refresh(self.textwindow.drawstate, self.textwindow.padview)
        self.textwindow.stdwin.move_cursor(self.textwindow.stdwin.stdcurs)# }}}

    def on_quit(self, e: QuitEvent):
        """Callback for the user quitting, display confirmation dialog if# {{{
        one is provided"""
        if e.confirm_dialog is None:
            self.textwindow.stdwin.quit()
        else:
            self.textwindow.event_handler.enqueue(OpenDialogEvent(e.confirm_dialog))# }}}

    def on_open_dialog(self, e: OpenDialogEvent):
        """Callback for opening a dialog box"""# {{{
        if self.state is GameState.INITIALISING:
            return

        self.unbind_movement_events()
        self.unmap_game_controls()
        if self.state not in (GameState.WIN, GameState.LOSE):
            self.unbind_game_events()

        dialog = e.dialog
        dialog.textwindow.drawstate.on_draw = dialog.on_draw
        dialog.bind_events()
        dialog.textwindow.stdwin.refresh()# }}}

    def on_restore_from_dialog(self, e: DialogRestoreEvent):
        """Callback for restoring from a closing dialog box"""# {{{
        dialog = e.dialog
        dialog.unbind_events()
        self.bind_movement_events()
        self.map_game_controls()
        if self.state not in (GameState.WIN, GameState.LOSE):
            self.bind_game_events()

        dialog.textwindow.drawstate.on_draw = None
        dialog.textwindow.drawstate.win.erase()
        dialog.textwindow.padview.desired_screen_start = (0, 0)
        dialog.textwindow.padview.desired_view_size = (0, 0)
        self.textwindow.stdwin.refresh()
        self.focus_cursor()# }}}

    def starting_playing(self):
        """Bind events to start playing the minesweeper game"""# {{{
        self.bind_movement_events()
        self.bind_game_events()
        self.bind_dialog_events()
        self.state = GameState.PLAYING# }}}

    def bind_movement_events(self):
        """Bind movement events"""# {{{
        self.textwindow.event_handler.bind(MovementEvent, self.on_grid_selection_changed)# }}}

    def unbind_movement_events(self):
        """Unbind movement events# {{{

        Return False if movement events are currently inactive"""
        self.textwindow.event_handler.unbind(MovementEvent)# }}}

    def bind_game_events(self):
        """Bind game events"""# {{{
        self.textwindow.event_handler.bind(SelectEvent, self.on_select)
        self.textwindow.event_handler.bind(PlaceFlagEvent, self.on_flag)
        self.textwindow.event_handler.bind(GameLoseEvent, self.on_lose)
        self.textwindow.event_handler.bind(GameWinEvent, self.on_win)# }}}

    def unbind_game_events(self):
        """Unbind game events# {{{

        Return False if game events are not currently active"""
        self.textwindow.event_handler.unbind(SelectEvent)
        self.textwindow.event_handler.unbind(PlaceFlagEvent)
        self.textwindow.event_handler.unbind(GameLoseEvent)
        self.textwindow.event_handler.unbind(GameWinEvent)# }}}

    def bind_dialog_events(self):
        """Bind dialog handling events"""# {{{
        self.last_quit_callback = self.textwindow.event_handler.rebind(QuitEvent, self.on_quit)
        self.textwindow.event_handler.bind(OpenDialogEvent, self.on_open_dialog)
        self.textwindow.event_handler.bind(DialogRestoreEvent, self.on_restore_from_dialog)# }}}

    def unbind_dialog_events(self):
        """Unbind dialog handling events# {{{

        Return False if dialog handling events are not currently active"""
        if self.last_quit_callback is not None:
            self.textwindow.event_handler.rebind(QuitEvent, self.last_quit_callback)
        self.textwindow.event_handler.unbind(OpenDialogEvent)
        self.textwindow.event_handler.unbind(DialogRestoreEvent)# }}}

    def draw_grid(self, win: curses.window, *, lose_coords: tuple[int, int] | None = None):
        """Draw the grid to the window"""# {{{
        tui.win_addlines(win, gridlines(self.grid))

        for coords, _ in self.grid:
            symbol = get_symbol_for_coord_from(self.grid, coords)
            if symbol is not None and coords == lose_coords:
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol, ATTR_RED)
            elif symbol is not None:
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol)# }}}

    def resize(self):
        """Resize the window view to fill the available space"""# {{{
        height, width = scale_grid_coords_to_screen_offset(self.grid.grid_size)
        width = width - 1
        width = clamp(width, curses.COLS - 3)
        height = clamp(height, curses.LINES - 4)
        starty = 2
        startx = (curses.COLS - width) // 2
        self.textwindow.padview.desired_screen_start = (starty, startx)
        self.textwindow.padview.desired_view_size = (height, width)# }}}

    def reveal_tile_at(self, coords: tuple[int, int]):
        """Reveal the tile at the specified coord"""# {{{
        tile = self.grid.get_tile(coords)
        if Tile.SEEN in tile or Tile.FLAG in tile:
            return

        tile |= Tile.SEEN
        self.grid.set_tile(coords, tile)
        self.mark_tile_at(coords)

        if Tile.MINE in tile:
            self.textwindow.event_handler.enqueue(GameLoseEvent(coords))
            return

        neighbour_coords = list(iter_3x3_area_coords(self.grid.grid_size, coords))
        neighbour_tiles = (self.grid.get_tile(neighbour) for neighbour in neighbour_coords)
        if sum(Tile.MINE in t for t in neighbour_tiles) == 0:
            for neighbour in neighbour_coords:
                self.reveal_tile_at(neighbour)

        n_remaining_empty_tiles = sum(Tile.EMPTY in t and Tile.SEEN not in t for _, t in self.grid)
        if n_remaining_empty_tiles == 0:
            self.textwindow.event_handler.enqueue(GameWinEvent())
            return# }}}

    def reveal_all_mines(self):
        """Reveal all the mines in the grid"""# {{{
        grid_changes = [(coords, tile | Tile.TRANS)
                        for coords, tile in self.grid
                        if Tile.MINE in tile]

        for coords, tile in grid_changes:
            self.grid.set_tile(coords, tile)
            self.mark_tile_at(coords)# }}}

    def focus_cursor(self):
        """Focus screen cursor to grid selection"""# {{{
        # TODO check if gameview has focus
        stdwin = self.textwindow.stdwin
        stdwin.stdcurs = get_grid_view_screen_cursor(self.textwindow.padview, self.selection)
        stdwin.move_cursor(stdwin.stdcurs)# }}}

    def mark_tile_at(self, coords: tuple[int, int]):
        """Mark the tile at the specified coords to be updated on the next refresh"""# {{{
        w, h = self.grid.grid_size
        x, y = coords
        assert 0 <= x < w and 0 <= y < h
        symbol = get_symbol_for_coord_from(self.grid, coords)
        symbol = ' ' if symbol is None else symbol
        self.textwindow.window.addch(*scale_grid_coords_to_screen_offset(coords), symbol)# }}}

    def update_mine_counter(self, win: curses.window):
        """Update the mine counter line"""# {{{
        status_line_y = get_grid_height(self.grid.grid_size)
        tui.win_clear_line(win, status_line_y)
        win.addstr(status_line_y, 0, f'Mines left: {self.grid.mines}',
                   ATTR_CYAN)# }}}

    def refresh(self):
        """Update the window with any marked tiles"""# {{{
        self.textwindow.window.refresh(*tui.padview_clamp(self.textwindow.padview))
        self.textwindow.stdwin.move_cursor(self.textwindow.stdwin.stdcurs)# }}}

    def map_game_controls(self):
        """Map keys for game controls"""# {{{
        stdwin = self.textwindow.stdwin
        event_handler = self.textwindow.event_handler
        stdwin.add_mapping(tui.askey(" "), partial(event_handler.enqueue, SelectEvent()))
        stdwin.add_mapping(tui.askey("f"), partial(event_handler.enqueue, PlaceFlagEvent()))# }}}

    def unmap_game_controls(self):
        """Remove mappings for game controls"""# {{{
        self.textwindow.stdwin.remove_mapping(tui.askey(" "))
        self.textwindow.stdwin.remove_mapping(tui.askey("f"))# }}}

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
        """Callback for drawing window"""# {{{
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
        return True# }}}

    def on_selection_changed(self, e: MovementEvent):
        """Callback to changing the selection"""# {{{
        delta = e.x if e.x != 0 else e.y
        self.choice = (self.choice + delta) % len(self.options)
        self.reposition_cursor()# }}}

    def on_select(self, _):
        """Callback for selecting an option"""# {{{
        assert self.choice < len(self.options)
        selection = self.options[self.choice]
        if selection.callback is not None:
            selection.callback()

        if selection.do_restore:
            self.textwindow.event_handler.enqueue(DialogRestoreEvent(self))# }}}

    def reposition_cursor(self):
        """Reposition the screen cursor to the selection"""# {{{
        stdwin = self.textwindow.stdwin
        sy, sx = self.textwindow.padview.desired_screen_start
        cy = len(self.message) + self.choice + sy + 1
        stdwin.stdcurs.cursor = (cy, sx)
        stdwin.move_cursor(stdwin.stdcurs)# }}}

    def bind_events(self):
        """Bind events for option dialog"""# {{{
        event_handler = self.textwindow.event_handler
        event_handler.bind(MovementEvent, self.on_selection_changed)
        event_handler.bind(SelectEvent, self.on_select)# }}}

    def unbind_events(self):
        """Unbind events after use"""# {{{
        event_handler = self.textwindow.event_handler
        event_handler.unbind(MovementEvent)
        event_handler.unbind(SelectEvent)# }}}

class MinesweeperApp:
    """Main application class for marshalling initialisation and program state"""
    __slots__ = ("stdwin", "event_handler", "gameview", "keyhelp", "overlay", "titlebar",
                 "debug_panel")

    def __init__(self, stdwin: tui.MainWindow):
        self.stdwin = stdwin# {{{
        self.event_handler = tui.EventHandler()
        self.stdwin.on_post_key = self.event_handler.process

        self.gameview = GameView(self.stdwin, self.event_handler, empty_tile_grid((10, 10), 15))
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
        self.gameview.starting_playing()
        self.gameview.map_game_controls()
        self.stdwin.mainloop() # }}}

    def on_resize(self):
        """Callback for window resizing"""# {{{
        curses.update_lines_cols()
        self.gameview.resize()
        self.gameview.focus_cursor()
        self.stdwin.refresh()# }}}

    def on_reset(self):
        """Callback for window reset/refresh"""# {{{
        self.stdwin.stdscr.clear()
        self.stdwin.refresh()# }}}

    def on_quit(self):
        """Callback for the user quitting the program# {{{

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
                default_height = get_grid_height(self.gameview.grid.grid_size))

        self.event_handler.enqueue(QuitEvent(confirm_dialog = quit_dialog))# }}}

    def do_quit(self):
        """Quit the mainloop"""# {{{
        self.stdwin.quit()# }}}

    def map_window(self):
        """Map the application keys for controlling the window state, such as# {{{
        screen refreshing, debug capabilities and quitting

        By default, quitting is bound to MinesweeperApp.do_quit, which ends the
        mainloop immediately, but this can be rebound by objects that handle
        displaying dialogs"""

        self.stdwin.add_mapping(tui.askey("KEY_RESIZE"), self.on_resize)
        self.stdwin.add_mapping(tui.askey("C-L"), self.on_reset)
        self.stdwin.add_mapping(tui.askey("g"), self.debug_panel.toggle)

        self.event_handler.bind(QuitEvent, lambda _: self.do_quit())
        self.stdwin.add_mapping(tui.askey("C-C"), self.on_quit)
        self.stdwin.add_mapping(tui.askey("q"), self.on_quit)# }}}

    def map_selection(self):
        """Map the directional keys to emit movement events"""# {{{
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

    def track_values(self):
        """Initialise the debug panel with tracked values"""# {{{
        self.debug_panel.track("cursor", lambda: self.stdwin.stdcurs)
        self.debug_panel.track("grid_coord", compose2(
            partial(getattr, self.gameview, "selection"), label_xycoords))

        gameview_pv = self.gameview.textwindow.padview
        self.debug_panel.track("pv_pad", compose2(
            partial(getattr, gameview_pv, "pad_start"), label_yxcoords))
        self.debug_panel.track("pv_screen", compose2(
            partial(getattr, gameview_pv, "desired_screen_start"), label_yxcoords))
        self.debug_panel.track("pv_view", compose2(
            partial(getattr, gameview_pv, "desired_view_size"), label_yxcoords)) # }}}

ATTR_NORMAL = curses.A_NORMAL
ATTR_UNDER  = curses.A_UNDERLINE

ATTR_BLUE:      int # initialised by init_curses
ATTR_CYAN:      int # initialised by init_curses
ATTR_GREEN:     int # initialised by init_curses
ATTR_MAGENTA:   int # initialised by init_curses
ATTR_RED:       int # initialised by init_curses
ATTR_WHITE:     int # initialised by init_curses
ATTR_YELLOW:    int # initialised by init_curses

def init_curses(_):
    """Initialise the curses library"""# {{{
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

def empty_tile_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:
    """Create an empty grid"""# {{{
    return TileGrid([], grid_size, mines) # }}}

def iter_conds_from_tiles(tiles: Iterable[Tile]) -> Iterable[bool]:
    """Return an iterator of barrier conditions for a collection of tiles"""# {{{
    for first_tile, second_tile in pairwise(tiles):
        yield Tile.SEEN not in first_tile or Tile.SEEN not in second_tile# }}}

def iter_elems_from_grid_y(grid: TileGrid, y: int) -> Iterable[str]:
    """Return gridline elements for the specified y-coordinate in grid"""# {{{
    width, _ = grid.grid_size
    conds = iter_conds_from_tiles(grid.get_tile((x, y)) for x in range(width))
    return (L_ns if cond else " " for cond in conds)# }}}

def iter_elems_from_grid_x(grid: TileGrid, x: int) -> Iterable[str]:
    """Return gridline elements for the specified x-coordinate in grid"""# {{{
    _, height = grid.grid_size
    conds = iter_conds_from_tiles(grid.get_tile((x, y)) for y in range(height))
    return (L_ew if cond else " " for cond in conds)# }}}

def empty_gridlines(grid_size: tuple[str, str]):
    """Return a list of strings representing an empty grid of specified size"""# {{{
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
    return lines# }}}

CELL_WIDTH = 3

def format_row_from_elems(elems: Iterable[str]) -> str:
    """Format a gridline row from row elements"""# {{{
    cell = " " * CELL_WIDTH
    inner = cell.join(elems)
    return f"{L_ns}{cell}{inner}{cell}{L_ns}"# }}}

def is_barrier(ch: str) -> bool:
    """Return True if character is considered a barrier symbol"""# {{{
    return ch != " "# }}}

# TODO try rewriting
def join_barriers(north: str, east: str, south: str, west: str) -> str:
    """Return symbol joining barriers in four directions"""# {{{
    n = is_barrier(north)
    e = is_barrier(east)
    s = is_barrier(south)
    w = is_barrier(west)
    result = " "
    if n and e and s and w:
        result = L_nesw
    elif n and e and w:
        result = L_new
    elif e and s and w:
        result = L_esw
    elif n and s and w:
        result = L_nsw
    elif n and e and s:
        result = L_nes
    elif n and w:
        result = L_nw
    elif n and e:
        result = L_ne
    elif s and w:
        result = L_sw
    elif e and s:
        result = L_es
    elif n and s:
        result = L_ns
    elif e and w:
        result = L_ew
    return result# }}}

def format_grid_top_border(elems: Iterable[str]) -> str:
    """Format top gridline border from row elements"""# {{{
    cell = L_ew * CELL_WIDTH
    inner = cell.join(L_esw if is_barrier(e) else L_ew for e in elems)
    return f"{C_es}{cell}{inner}{cell}{C_sw}"# }}}

def format_grid_bottom_border(elems: Iterable[str]) -> str:
    """Format bottom gridline border from row elements"""# {{{
    cell = L_ew * CELL_WIDTH
    inner = cell.join(L_new if is_barrier(e) else L_ew for e in elems)
    return f"{C_ne}{cell}{inner}{cell}{C_nw}"# }}}

def format_sep_line(sep: Iterable[str], above_row: Iterable[str], below_row: Iterable[str]) -> str:
    """Format seperator line between rows"""# {{{
    isep = iter(sep)
    before_elem = next(isep)
    sep_line = L_nes if is_barrier(before_elem) else L_ns
    sep_line += before_elem * CELL_WIDTH

    for after_elem, above_elem, below_elem in zip(isep, above_row, below_row):
        sep_line += join_barriers(above_elem, after_elem, below_elem, before_elem)
        sep_line += after_elem * CELL_WIDTH
        before_elem = after_elem

    sep_line += L_nsw if is_barrier(before_elem) else L_ns
    return sep_line# }}}

def gridlines(grid: TileGrid) -> list[str]:
    """Return a list of strings corresponding to the text lines representing# {{{
    the grid"""
    if grid.empty():
        return empty_gridlines(grid.grid_size)

    width, height = grid.grid_size
    rows = [list(iter_elems_from_grid_y(grid, y)) for y in range(height)]
    seps = transpose_2d([list(iter_elems_from_grid_x(grid, x)) for x in range(width)])

    irows = iter(rows)
    above_row = next(irows)
    lines = []
    lines.append(format_grid_top_border(above_row))
    lines.append(format_row_from_elems(above_row))
    for sep, below_row in zip(seps, irows):
        lines.append(format_sep_line(sep, above_row, below_row))
        lines.append(format_row_from_elems(below_row))
        above_row = below_row

    lines.append(format_grid_bottom_border(above_row))
    return lines# }}}

def label_yxcoords(coords: tuple[int, int]) -> str:
    """Format a string with coordinates in y-x order"""# {{{
    return label_tuple(coords, "y", "x") # }}}

def label_xycoords(coords: tuple[int, int]) -> str:
    """Format a string with coordinates in x-y order"""# {{{
    return label_tuple(coords, "x", "y") # }}}

def iter_3x3_area_coords(grid_size: tuple[int, int], coords: tuple[int, int]) -> Iterable[Tile]:
    """Return an iterator of coordinates in a 3x3 area cetnered around# {{{
    specified coords for a specified grid size"""
    thisx, thisy = coords
    width, height = grid_size
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            x = i + thisx
            y = j + thisy
            if 0 <= x < width and 0 <= y < height:
                yield (x, y)# }}}

def iter_grid_neighbours(grid: TileGrid, coords: tuple[int, int]) -> Iterable[Tile]:
    """Return an iterator of neighbouring tiles to specfied grid coordinates"""# {{{
    thisx, thisy = coords
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            if y == 0 and x == 0:
                continue
            if (neighbour := grid.get_maybe_tile((thisx + x, thisy + y))) is None:
                continue
            yield neighbour# }}}

def count_neighbouring_mines(grid: TileGrid, coords: tuple[int, int]) -> int:
    """Count the number of mines neighbouring the specified coordinates in the# {{{
    specified grid"""
    return sum(Tile.MINE in t for t in iter_grid_neighbours(grid, coords))# }}}

def get_symbol_for_coord_from(grid: TileGrid, coords: tuple[int, int]) -> str | None:
    """Determine display symbol for grid coordinates"""# {{{
    tile = grid.get_tile(coords)
    symbol: str | None = None
    if Tile.MINE in tile and Tile.SEEN in tile:
        symbol = 'x'
    elif Tile.MINE in tile and Tile.TRANS in tile:
        symbol = 'x'
    elif Tile.FLAG in tile:
        symbol = 'f'
    elif Tile.SEEN not in tile:
        symbol = None
    else:
        n_neighbouring_mines = count_neighbouring_mines(grid, coords)
        symbol = ' ' if n_neighbouring_mines == 0 else str(n_neighbouring_mines)

    return symbol# }}}

def wrap_coords_to_grid(coords: tuple[int, int], grid_size: tuple[int, int]) -> tuple[int, int]:
    """Calculate coordinates wrapped inside a grid"""# {{{
    x, y = coords
    w, h = grid_size
    return (x % w, y % h) # }}}

def scale_grid_coords_to_screen_offset(grid_coords: tuple[int, int]) -> tuple[int, int]:
    """Scale grid coordinates to offset from the origin of the grid window"""# {{{
    x, y = grid_coords
    return (2 * y + 1, 4 * x + 2)# }}}

def get_grid_view_screen_cursor(
        grid_view: tui.PadView, selection_coords: tuple[int, int]) -> tui.Cursor:
    """Calculate screen coordinates for a given coordinate in a grid"""# {{{
    y, x = scale_grid_coords_to_screen_offset(selection_coords)
    starty, startx = grid_view.desired_screen_start
    pady, padx = grid_view.pad_start
    return tui.Cursor((starty - pady + y, startx - padx + x))#}}}

def get_grid_height(grid_size: tuple[int, int]) -> int:
    """Calculate height of grid in window from its grid size"""# {{{
    _, height = grid_size
    return 2 * height + 1# }}}

def key_instruction_bar(stdwin: tui.MainWindow, event_handler: tui.EventHandler) -> tui.TextWindow:
    """Object for drawing key instructions"""# {{{
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
            drawstate)# }}}

def overlay(stdwin: tui.MainWindow, event_handler: tui.EventHandler):
    """Object for drawing dialogs overlaying the application"""# {{{
    window = curses.newpad(100, 100)
    padview = tui.PadView(window)
    drawstate = tui.WindowDrawState(window)
    stdwin.add_child(drawstate, padview)
    return tui.TextWindow(
            stdwin,
            event_handler,
            drawstate,
            padview)# }}}

def titlebar(stdwin: tui.MainWindow, event_handler: tui.EventHandler):
    """Object for drawing the application titlebar"""# {{{
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
            drawstate)# }}}

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=marker
