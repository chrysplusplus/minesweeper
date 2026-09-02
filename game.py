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

from dialog import DialogLike, MovementEvent, SelectEvent, OpenDialogEvent, DialogRestoreEvent
from event import BaseEvent, EventHandler
from util import clamp, label_tuple, transpose_2d

from boxsym import (
        L_ew, L_ns,
        L_es, L_sw, L_ne, L_nw,
        L_nes, L_nsw, L_esw, L_new,
        L_nesw,
        C_es, C_sw, C_nw, C_ne)

class PlaceFlagEvent(BaseEvent):
    """Event class for placing flags at the current selection"""

@dataclass(slots = True)
class QuitEvent(BaseEvent):
    """Event class for the user quitting the program"""
    _: KW_ONLY
    confirm_dialog: DialogLike | None = None

@dataclass(slots = True)
class GameLoseEvent(BaseEvent):
    """Event class for the user losing the game"""
    coords: tuple[int, int]

@dataclass(slots = True)
class GameWinEvent(BaseEvent):
    """Event class for the user winning the game"""

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

class GameState(Enum):
    """Enumeration of possible states for GameView"""
    INITIALISING = auto()
    PLAYING = auto()
    WIN = auto()
    LOSE = auto()

@dataclass(slots = True)
class GameViewParameters:
    """Class detailing input parameters for a initialising GameView object"""
    _: KW_ONLY
    stdwin: tui.MainWindow
    event_handler: EventHandler
    grid: TileGrid

# TODO check these notes
# NOTE pylint gives R0904: Too many public methods
class GameView:
    """Class for drawing the Minesweeper grid and handling game logic"""
    __slots__ = ("textwindow", "selection", "state", "grid", "last_quit_callback")

    def __init__(self, params: GameViewParameters):
        window = curses.newpad(100, 100)# {{{
        padview = tui.PadView(window, desired_screen_start = (2, 0))
        drawstate = tui.WindowDrawState(window)
        drawstate.on_draw = self.on_game_draw
        params.stdwin.add_child(drawstate, padview)

        self.textwindow = tui.TextWindow(params.stdwin, params.event_handler, drawstate, padview)
        self.selection = (0, 0)
        self.state = GameState.INITIALISING
        self.grid = params.grid
        # TODO dialog handling class
        self.last_quit_callback: Callable[[BaseEvent], None] | None = None# }}}

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
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You lose!", term.ATTR_RED)
        return True# }}}

    def on_win_draw(self, win: curses.window) -> bool:
        """Callback for drawing after winning the game"""# {{{
        win.erase()
        self.draw_grid(win)
        win.addstr(get_grid_height(self.grid.grid_size), 0, "You win!", term.ATTR_YELLOW)
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
                win.addch(*scale_grid_coords_to_screen_offset(coords), symbol, term.ATTR_RED)
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
                   term.ATTR_CYAN)# }}}

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

def make_game_view(**kwargs) -> GameView:
    """Helper function for initialising GameView

    See GameViewParameters for parameter names and corresponding types. Returns
    a GameView"""
    return GameView(GameViewParameters(**kwargs))

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

# vim: foldmethod=marker
