"""File: game.py
Author: chrysplusplus
Date: 2026-08-30

Module for handling game and game display logic"""

import curses

from collections.abc import Callable, Iterable
from dataclasses import dataclass, KW_ONLY
from enum import Flag, auto, Enum
from functools import partial
from itertools import repeat, pairwise
from random import shuffle

import tui
import terminal as term

from dialog import MovementEvent, SelectEvent, QuitEvent, OpenDialogEvent, DialogRestoreEvent,\
        DialogLike, Option, OptionsDialog
from event import BaseEvent, EventHandler
from util import clamp, label_tuple, transpose_2d

from boxsym import (
        L_ew, L_ns,
        L_nes, L_nsw, L_esw, L_new,
        L_nesw,
        C_es, C_sw, C_nw, C_ne,
        make_connector)

@dataclass(slots = True)
class PlaceFlagEvent(BaseEvent):
    """Event class for placing flags at the current selection"""

@dataclass(slots = True)
class GameLoseEvent(BaseEvent):
    """Event class for the user losing the game"""
    coords: tuple[int, int]

@dataclass(slots = True)
class GameWinEvent(BaseEvent):
    """Event class for the user winning the game"""

@dataclass(slots = True)
class NewGameEvent(BaseEvent):
    """Event class for a new game"""

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
        assert mines < (grid_size[0] * grid_size[1])
        self._grid: list[Tile] = grid
        self._grid_size = grid_size
        self._mines = mines
        self._flags = 0

    def __iter__(self) -> Iterable[tuple[tuple[int, int], Tile]]:
        width, _ = self._grid_size
        for i, tile in enumerate(self._grid):
            y, x = divmod(i, width)
            yield ((x, y), tile)

    @property
    def grid_size(self):
        """Size of the grid, read-only"""
        return self._grid_size

    @property
    def mines(self):
        """Number of mines remaining in the grid, read-only"""
        return self._mines - self._flags#

    def get_tile(self, coord: tuple[int, int]) -> Tile:
        """Get tile at coordinate"""
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        return self._grid[y * width + x]

    def set_tile(self, coord: tuple[int, int], tile: Tile):
        """Set tile at coordinate"""
        width, height = self._grid_size
        x, y = coord
        assert width > x >= 0 and height > y >= 0
        self._check_flag(coord, tile)
        self._grid[y * width + x] = tile

    def get_maybe_tile(self, coord: tuple[int, int]) -> Tile | None:
        """Get tile at coordinate if one exists there"""
        width, height = self._grid_size
        x, y = coord
        return self._grid[y * width + x] \
                if width > x >= 0 and height > y >= 0 \
                else None

    def get_total_mines(self) -> int:
        """Get the total number of mines"""
        return self._mines

    def empty(self) -> bool:
        """Return True if the grid is empty and unpopulated"""
        return len(self._grid) == 0

    def populate_except_for(self, *except_coords: tuple[int, int]):
        """Populate grid from grid_size and mines, avoiding specified coords"""
        width, height = self._grid_size
        locations = [(x, y) for x in range(width) for y in range(height)
                     if (x, y) not in except_coords]
        shuffle(locations)

        self._grid = [Tile.EMPTY for _ in range(width) for _ in range(height)]
        for minex, miney in locations[:self._mines]:
            self._grid[miney * width + minex] = Tile.MINE

    def _check_flag(self, coord: tuple[int, int], new_tile: Tile):
        """Determine whether changing tile affects the flag count"""
        x, y = coord
        width, _ = self._grid_size
        old_tile = self._grid[y * width + x]
        if Tile.FLAG in old_tile and Tile.FLAG not in new_tile:
            self._flags -= 1
        elif Tile.FLAG not in old_tile and Tile.FLAG in new_tile:
            self._flags += 1

class GameState(Enum):
    """Enumeration of possible states for GameLogic"""
    INITIALISING = auto()
    PLAYING = auto()
    WIN = auto()
    LOSE = auto()

class GridDisplay:
    """Handles drawing the tile grid"""
    __slots__ = ("stdwin", "grid", "selection", "padview", "drawstate")

    def __init__(self, stdwin: tui.MainWindow, grid: TileGrid):
        self.stdwin = stdwin
        self.grid = grid
        self.selection = (0, 0)

        window = curses.newpad(100, 100)
        self.padview = tui.PadView(window, desired_screen_start = (2, 0))
        self.drawstate = tui.WindowDrawState(window)
        self.stdwin.add_child(self.drawstate, self.padview)

        self.set_draw_callback(self.on_play_draw)

    def on_play_draw(self, win: curses.window) -> bool:
        """Callback for drawing during play state"""
        win.erase()
        self.draw_grid(win)
        self.update_mine_counter(win)
        return True

    def on_lose_draw(self, win: curses.window, *, lose_coords: tuple[int, int]) -> bool:
        """Callback for drawing during lose state"""
        win.erase()
        self.draw_grid(win, lose_coords = lose_coords)
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You lose!", term.ATTR_RED)
        return True

    def on_win_draw(self, win: curses.window) -> bool:
        """Callback for drawing after winning the game"""
        win.erase()
        self.draw_grid(win)
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You win!", term.ATTR_YELLOW)
        return True

    def get_grid_selection_coords(self) -> tuple[int, int]:
        """Return the coords of the current grid selection"""
        return self.selection

    def set_draw_callback(self, callback: Callable[[curses.window], bool])\
            -> Callable[[curses.window], bool] | None:
        """Set the draw callback for the display

        Returns the old callback"""
        old_callback, self.drawstate.on_draw = self.drawstate.on_draw, callback
        return old_callback

    def set_grid(self, grid: TileGrid):
        """Set the grid and reset the grid selection"""
        self.grid = grid
        self.selection = (0, 0)
        self.set_draw_callback(self.on_play_draw)
        self.redraw()

    def draw_grid(self, win: curses.window, **kwargs):
        """Draw the grid to the window

        kwargs:
            loords_coords: tuple[int, int]"""
        lose_coords = kwargs.get("lose_coords")
        tui.win_addlines(win, gridlines(self.grid))
        for coords, _ in self.grid:
            symbol = get_symbol_for_coord_from(self.grid, coords)
            if symbol is not None and coords == lose_coords:
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol, term.ATTR_RED)
            elif symbol is not None:
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol)

    def mark_tile_at(self, coords: tuple[int, int]):
        """Mark the tile at the specified coords

        Marked tiles are updated on the next refresh call"""
        w, h = self.grid.grid_size
        x, y = coords
        assert 0 <= x < w and 0 <= y < h
        symbol = get_symbol_for_coord_from(self.grid, coords)
        symbol = ' ' if symbol is None else symbol
        self.drawstate.win.addch(*scale_grid_coords_to_screen_offset(coords), symbol)

    def toggle_flag_at_selection(self):
        """Toggle the flag on the selected tile"""
        old_tile = self.grid.get_tile(self.selection)
        if Tile.SEEN in old_tile:
            return

        new_tile = old_tile ^ Tile.FLAG
        self.grid.set_tile(self.selection, new_tile)
        self.mark_tile_at(self.selection)
        self.update_mine_counter(self.drawstate.win)
        self.refresh()

    def focus_cursor(self):
        """Focus screen cursor to grid selection"""
        self.stdwin.stdcurs = get_grid_view_screen_cursor(self.padview, self.selection)
        self.stdwin.move_cursor(self.stdwin.stdcurs)

    def move_selection_relative(self, dx: int, dy: int):
        """Move the grid cursor by relative coordinates"""
        x, y = self.selection
        self.selection = wrap_coords_to_grid((x + dx, y + dy), self.grid.grid_size)
        self.focus_cursor()

    def update_mine_counter(self, win: curses.window):
        """Update the mine counter line"""
        status_line_y = get_grid_height(self.grid.grid_size)
        tui.win_clear_line(win, status_line_y)
        win.addstr(status_line_y, 0, f'Mines left: {self.grid.mines}', term.ATTR_CYAN)

    def resize(self):
        """Resize the drawing surface to fill the available space"""
        height, width = scale_grid_coords_to_screen_offset(self.grid.grid_size)
        width = width - 1
        width = clamp(width, curses.COLS - 3)
        height = clamp(height, curses.LINES - 4)
        starty = 2
        startx = (curses.COLS - width) // 2
        self.padview.desired_screen_start = (starty, startx)
        self.padview.desired_view_size = (height, width)

    def refresh(self):
        """Update the window with any marked tiles"""
        self.drawstate.win.refresh(*tui.padview_clamp(self.padview))
        self.focus_cursor()

    def redraw(self):
        """Redraw the whole surface"""
        tui.windraw_refresh(self.drawstate, self.padview)

class GameLogic:
    """Handles game controls and logic"""
    __slots__ = ("stdwin", "event_handler", "overlay", "display", "state", "grid")

    def __init__(self,
                 stdwin: tui.MainWindow,
                 event_handler: EventHandler,
                 grid: TileGrid):
        self.stdwin = stdwin
        self.event_handler = event_handler
        self.overlay: tui.TextWindow | None = None
        self.display = GridDisplay(stdwin, grid)
        self.grid = grid
        self.state = GameState.INITIALISING

    def on_grid_selection_changed(self, e: MovementEvent):
        """Callback for updating grid selection"""
        if not e.relative:
            raise NotImplementedError("Absolute grid motions not implemented")
        self.display.move_selection_relative(e.x, e.y)

    def on_select(self, _):
        """Callback for activating current selection"""
        if self.grid.empty():
            self.grid.populate_except_for(
                    *iter_3x3_area_coords(self.grid.grid_size, self.display.selection))

        self.reveal_tile_at(self.display.selection)
        self.display.redraw()
        self.display.focus_cursor()

    def on_lose(self, e: GameLoseEvent):
        """Callback for losing the game"""
        lose_coords = e.coords
        self.state = GameState.LOSE
        self.unbind_game_events()
        self.reveal_all_mines()
        self.display.set_draw_callback(
                partial(self.display.on_lose_draw, lose_coords = lose_coords))
        self.display.redraw()

    def on_win(self, _):
        """Callback for winning the game"""
        self.state = GameState.WIN
        self.unbind_game_events()
        self.display.set_draw_callback(self.display.on_win_draw)
        self.display.redraw()

    def on_quit(self, e: QuitEvent):
        """Callback for the user quitting

        If provided in the event data, a confirmation dialog is displayed"""
        if e.confirm_dialog is None:
            self.stdwin.quit()
        else:
            self.event_handler.enqueue(OpenDialogEvent(e.confirm_dialog))

    def on_open_dialog(self, e: OpenDialogEvent):
        """Callback for opening a dialog box"""
        if self.state is GameState.INITIALISING:
            return

        self.unbind_movement_events()
        self.unmap_game_controls()
        if self.state not in (GameState.WIN, GameState.LOSE):
            self.unbind_game_events()

        dialog = e.dialog
        dialog.textwindow.drawstate.on_draw = dialog.on_draw
        dialog.bind_events()
        self.stdwin.refresh()

    def on_restore_from_dialog(self, e: DialogRestoreEvent):
        """Callback for restoring from a closing dialog box"""
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
        self.stdwin.refresh()
        self.display.focus_cursor()

    def on_new_game(self, _):
        """Callback for new game"""
        if self.overlay is None:
            do_new_game()
            return

        if self.overlay.drawstate.on_draw is not None:
            return

        confirm_dialog = OptionsDialog(
                textwindow = self.overlay,
                message = ["Start a new game?"],
                options = [
                    Option("Yes", self.do_new_game, do_restore = True),
                    Option("No", do_restore = True)],
                choice = 1,
                default_height = get_grid_height(self.grid.grid_size))

        self.event_handler.enqueue(OpenDialogEvent(confirm_dialog))

    def do_new_game(self):
        """Callback after confirming new game"""
        if self.state is GameState.INITIALISING:
            return

        new_grid = empty_tile_grid(self.grid.grid_size, self.grid.get_total_mines())
        self.grid = new_grid
        self.display.set_grid(new_grid)

        if self.state in (GameState.WIN, GameState.LOSE):
            self.state = GameState.PLAYING
            self.bind_game_events()

    def set_overlay_surface(self, surface: tui.TextWindow) -> tui.TextWindow | None:
        """Set the surface for drawing overlay dialogs

        Returns the last overlay surface"""
        old_surface, self.overlay = self.overlay, surface
        return old_surface

    def start_playing(self):
        """Bind events to start playing the minesweeper game"""
        self.bind_movement_events()
        self.bind_game_events()
        self.bind_dialog_events()
        self.state = GameState.PLAYING

    def bind_movement_events(self):
        """Bind movement events"""
        self.event_handler.bind(MovementEvent, self.on_grid_selection_changed)

    def unbind_movement_events(self):
        """Unbind movement events"""
        self.event_handler.unbind(MovementEvent)

    def bind_game_events(self):
        """Bind game events"""
        self.event_handler.bind(SelectEvent, self.on_select)
        self.event_handler.bind(PlaceFlagEvent, lambda _: self.display.toggle_flag_at_selection())
        self.event_handler.bind(GameLoseEvent, self.on_lose)
        self.event_handler.bind(GameWinEvent, self.on_win)

    def unbind_game_events(self):
        """Unbind game events"""
        self.event_handler.unbind(SelectEvent)
        self.event_handler.unbind(PlaceFlagEvent)
        self.event_handler.unbind(GameLoseEvent)
        self.event_handler.unbind(GameWinEvent)

    def bind_dialog_events(self) -> Callable[[BaseEvent], None] | None:
        """Bind dialog handling events

        Returns the last quit callback for restoring later"""
        last_quit_callback = self.event_handler.rebind(QuitEvent, self.on_quit)
        self.event_handler.bind(OpenDialogEvent, self.on_open_dialog)
        self.event_handler.bind(DialogRestoreEvent, self.on_restore_from_dialog)

        self.event_handler.bind(NewGameEvent, self.on_new_game)
        self.stdwin.add_mapping(
                tui.askey("n"), lambda: self.event_handler.enqueue(NewGameEvent()))

        return last_quit_callback

    def unbind_dialog_events(self, next_quit_callback: Callable[[BaseEvent], None]):
        """Unbind dialog handling events

        Return False if dialog handling events are not currently active"""
        self.event_handler.rebind(QuitEvent, next_quit_callback)
        self.event_handler.unbind(OpenDialogEvent)
        self.event_handler.unbind(DialogRestoreEvent)

        self.event_handler.unbind(NewGameEvent)
        self.stdwin.remove_mapping(tui.askey("n"))

    def resize_drawing_surface(self):
        """Resize the drawing surface"""
        self.display.resize()
        self.display.focus_cursor()

    def reveal_tile_at(self, coords: tuple[int, int]):
        """Reveal the tile at the specified coord"""
        tile = self.grid.get_tile(coords)
        if Tile.SEEN in tile or Tile.FLAG in tile:
            return

        tile |= Tile.SEEN
        self.grid.set_tile(coords, tile)
        self.display.mark_tile_at(coords)

        if Tile.MINE in tile:
            self.event_handler.enqueue(GameLoseEvent(coords))
            return

        neighbour_coords = list(iter_3x3_area_coords(self.grid.grid_size, coords))
        neighbour_tiles = (self.grid.get_tile(neighbour) for neighbour in neighbour_coords)
        if sum(Tile.MINE in t for t in neighbour_tiles) == 0:
            for neighbour in neighbour_coords:
                self.reveal_tile_at(neighbour)

        n_remaining_empty_tiles = sum(Tile.EMPTY in t and Tile.SEEN not in t for _, t in self.grid)
        if n_remaining_empty_tiles == 0:
            self.event_handler.enqueue(GameWinEvent())
            return

    def reveal_all_mines(self):
        """Reveal all the mines in the grid"""
        grid_changes = [
                (coords, tile | Tile.TRANS)
                for coords, tile in self.grid
                if Tile.MINE in tile]

        for coords, tile in grid_changes:
            self.grid.set_tile(coords, tile)
            self.display.mark_tile_at(coords)

    def map_game_controls(self):
        """Map keys for game controls"""
        self.stdwin.add_mapping(tui.askey(" "), lambda: self.event_handler.enqueue(SelectEvent()))
        self.stdwin.add_mapping(
                tui.askey("f"), lambda: self.event_handler.enqueue(PlaceFlagEvent()))

    def unmap_game_controls(self):
        """Remove mappings for game controls"""
        self.stdwin.remove_mapping(tui.askey(" "))
        self.stdwin.remove_mapping(tui.askey("f"))

def empty_tile_grid(grid_size: tuple[int, int], mines: int) -> TileGrid:
    """Create an empty grid"""
    return TileGrid([], grid_size, mines)

def iter_conds_from_tiles(tiles: Iterable[Tile]) -> Iterable[bool]:
    """Return an iterator of barrier conditions for a collection of tiles"""
    for first_tile, second_tile in pairwise(tiles):
        yield Tile.SEEN not in first_tile or Tile.SEEN not in second_tile

def iter_elems_from_grid_y(grid: TileGrid, y: int) -> Iterable[str]:
    """Return gridline elements for the specified y-coordinate in grid"""
    width, _ = grid.grid_size
    conds = iter_conds_from_tiles(grid.get_tile((x, y)) for x in range(width))
    return (L_ns if cond else " " for cond in conds)

def iter_elems_from_grid_x(grid: TileGrid, x: int) -> Iterable[str]:
    """Return gridline elements for the specified x-coordinate in grid"""
    _, height = grid.grid_size
    conds = iter_conds_from_tiles(grid.get_tile((x, y)) for y in range(height))
    return (L_ew if cond else " " for cond in conds)

def empty_gridlines(grid_size: tuple[str, str]):
    """Return a list of strings representing an empty grid of specified size"""
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
    return lines

CELL_WIDTH = 3

def format_row_from_elems(elems: Iterable[str]) -> str:
    """Format a gridline row from row elements"""
    cell = " " * CELL_WIDTH
    inner = cell.join(elems)
    return f"{L_ns}{cell}{inner}{cell}{L_ns}"

def is_barrier(ch: str) -> bool:
    """Return True if character is considered a barrier symbol"""
    return ch != " "

def join_barriers(north: str, east: str, south: str, west: str) -> str:
    """Return symbol joining barriers in four directions"""
    connector = make_connector(
            north = is_barrier(north),
            east = is_barrier(east),
            south = is_barrier(south),
            west = is_barrier(west))

    return str(connector)

def format_grid_top_border(elems: Iterable[str]) -> str:
    """Format top gridline border from row elements"""
    cell = L_ew * CELL_WIDTH
    inner = cell.join(L_esw if is_barrier(e) else L_ew for e in elems)
    return f"{C_es}{cell}{inner}{cell}{C_sw}"

def format_grid_bottom_border(elems: Iterable[str]) -> str:
    """Format bottom gridline border from row elements"""
    cell = L_ew * CELL_WIDTH
    inner = cell.join(L_new if is_barrier(e) else L_ew for e in elems)
    return f"{C_ne}{cell}{inner}{cell}{C_nw}"

def format_sep_line(sep: Iterable[str], above_row: Iterable[str], below_row: Iterable[str]) -> str:
    """Format seperator line between rows"""
    isep = iter(sep)
    before_elem = next(isep)
    sep_line = L_nes if is_barrier(before_elem) else L_ns
    sep_line += before_elem * CELL_WIDTH

    for after_elem, above_elem, below_elem in zip(isep, above_row, below_row):
        sep_line += join_barriers(above_elem, after_elem, below_elem, before_elem)
        sep_line += after_elem * CELL_WIDTH
        before_elem = after_elem

    sep_line += L_nsw if is_barrier(before_elem) else L_ns
    return sep_line

def gridlines(grid: TileGrid) -> list[str]:
    """Return a list of strings corresponding to the text lines representing
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
    return lines

def label_yxcoords(coords: tuple[int, int]) -> str:
    """Format a string with coordinates in y-x order"""
    return label_tuple(coords, "y", "x")

def label_xycoords(coords: tuple[int, int]) -> str:
    """Format a string with coordinates in x-y order"""
    return label_tuple(coords, "x", "y")

def iter_3x3_area_coords(grid_size: tuple[int, int], coords: tuple[int, int]) -> Iterable[Tile]:
    """Return an iterator of coordinates in a 3x3 area cetnered around
    specified coords for a specified grid size"""
    thisx, thisy = coords
    width, height = grid_size
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            x = i + thisx
            y = j + thisy
            if 0 <= x < width and 0 <= y < height:
                yield (x, y)

def iter_grid_neighbours(grid: TileGrid, coords: tuple[int, int]) -> Iterable[Tile]:
    """Return an iterator of neighbouring tiles to specfied grid coordinates"""
    thisx, thisy = coords
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            if y == 0 and x == 0:
                continue
            if (neighbour := grid.get_maybe_tile((thisx + x, thisy + y))) is None:
                continue
            yield neighbour

def count_neighbouring_mines(grid: TileGrid, coords: tuple[int, int]) -> int:
    """Count the number of mines neighbouring the specified coordinates in the
    specified grid"""
    return sum(Tile.MINE in t for t in iter_grid_neighbours(grid, coords))

def get_symbol_for_coord_from(grid: TileGrid, coords: tuple[int, int]) -> str | None:
    """Determine display symbol for grid coordinates"""
    tile = grid.get_tile(coords)
    symbol: str | None = None
    # TODO add setting to change these to ASCII symbols
    if Tile.MINE in tile and Tile.SEEN in tile:
        symbol = '💣'
    elif Tile.MINE in tile and Tile.TRANS in tile:
        symbol = '💣'
    elif Tile.FLAG in tile:
        symbol = '🚩'
    elif Tile.SEEN not in tile:
        symbol = None
    else:
        n_neighbouring_mines = count_neighbouring_mines(grid, coords)
        symbol = ' ' if n_neighbouring_mines == 0 else str(n_neighbouring_mines)

    return symbol

def wrap_coords_to_grid(coords: tuple[int, int], grid_size: tuple[int, int]) -> tuple[int, int]:
    """Calculate coordinates wrapped inside a grid"""
    x, y = coords
    w, h = grid_size
    return (x % w, y % h)

def scale_grid_coords_to_screen_offset(grid_coords: tuple[int, int]) -> tuple[int, int]:
    """Scale grid coordinates to offset from the origin of the grid window"""
    x, y = grid_coords
    return (2 * y + 1, 4 * x + 2)

def get_grid_view_screen_cursor(
        grid_view: tui.PadView, selection_coords: tuple[int, int]) -> tui.Cursor:
    """Calculate screen coordinates for a given coordinate in a grid"""
    y, x = scale_grid_coords_to_screen_offset(selection_coords)
    starty, startx = grid_view.desired_screen_start
    pady, padx = grid_view.pad_start
    return tui.Cursor((starty - pady + y, startx - padx + x))#

def get_grid_height(grid_size: tuple[int, int]) -> int:
    """Calculate height of grid in window from its grid size"""
    _, height = grid_size
    return 2 * height + 1
