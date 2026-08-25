"""
File: tui.py
Author: chrysplusplus
Date: 2026-06-18

Rather than being a wrapper library around curses, this module is intended to
complement it, providing actual support for Unicode character entry through the
Key dataclass and its associated functions, as well as a very rudimentary event
callback mainloop with the MainWindow class.

Note that all of this is optional -- you can completely avoid using MainWindow
if you don't need it, or you can subclass it and completely overhaul the key
mapping system with your own. I don't want this library to dictate style, when
function should really be the focus.

Regarding the Unicode utf8_len function, my testing of this is admittedly
limited. This came about because I was tired of having a non-US keyboard layout
and curses.getstr reporting the wrong character. Because this is such a niche
issue (or perhaps because of the decaying state of contemporary internet search
results) it was incredibly hard to find information on this strange behaviour,
and for a while I was using a non-blocking method cobbled together from blog
posts and answers on stackoverflow, which worked, but was incredibly
CPU-intensive. More recently, I was reading through the curses Python
documenttion and started experimenting with the curses.getch function, which I
had used in my non-blocking temporary solution without fully understanding what
it did. I'll save the explanation for now, but it turns out that getch works
the same whether the library is set to delay or nodelay (blocking and
non-blocking, respectively), except that in the non-blocking context, getch
returns -1 as a sentinel value for the end of a byte stream. In the blocking
context, no such sentinel exists, which is why I thought it wasn't possible to
parse Unicode input in this situation. However, getch actually returns each
byte of a Unicode input on successive calls, though this behaviour isn't
apparent in the "tutorial" mainloop key handling for curses, which led me to
believe that the function truncated the whole codepoint to its final byte. The
leading bytes actually get eaten by the mainloop, which then blocks on the next
call to getch, so the observed previous value is the last byte of the previous
input and the last byte only. Now I have realised this, I rewrote my input
handling code to examine the value returned by getch and attempt to detect if
it beyond ASCII range and calculate how many more calls to getch are required
to obtain the rest of the Unicode input -- this is essentially a description of
what utf8_len does.

There are two ways to use MainWindow:

• Obtain stdscr yourself, either through curses.initscr or curses.wrapper, and
  then construct MainWindow with the stdscr -- technically, you could pass any
  curses.window to this constructor, but this isn't tested.

• Call curses.wrapper with start_curses, which lets you pass in your own
  initialisation code and then the entry point for the program that interfaces
  with the MainWindow object wrapping stdscr.

The start_curses interface is designed to embody the philosophy that this
module complements curses but does not wrap it. Not the difference between this

>>> start_curses(init_fn, main_fn, cmd_args)

and this

>>> curses.wrapper(start_curses, init_fn, main_fn, cmd_args)

While more verbose, it clearly communicates that knowledge of how to use the
curses library is still required, only that using this library will help makes
certain parts of that usage easier."""

import curses
import curses.ascii as cascii

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, KW_ONLY
from typing import TypeVar

from util import clamp

T = TypeVar('T')

linechars = [#      1    2    3    4    5{{{
             "00", "─", "│",
             "03", "┌", "┐", "└", "┘",
             "08", "├", "┤", "┬", "┴", "┼",
             "14", "═", "║",
             "17", "╒", "╓", "╔",
             "21", "╕", "╖", "╗",
             "25", "╘", "╙", "╚",
             "29", "╛", "╜", "╝",
             "33", "╞", "╟", "╠",
             "37", "╡", "╢", "╣",
             "41", "╤", "╥", "╦",
             "45", "╧", "╨", "╩",
             "49", "╪", "╫", "╬",
             "53", "╭", "╮", "╯", "╰" ]# }}}

L_ew, L_ns                         = linechars[1],  linechars[2]# {{{
L_es, L_sw, L_ne, L_nw             = linechars[4],  linechars[5],  linechars[6],  linechars[7]
L_nes, L_nsw, L_esw, L_new, L_nesw = linechars[9],  linechars[10], linechars[11], linechars[12],\
        linechars[13]
L_EW, L_NS                         = linechars[15], linechars[16]
L_Es, L_eS, L_ES                   = linechars[18], linechars[19], linechars[20]
L_Sw, L_Sw, L_SW                   = linechars[22], linechars[23], linechars[24]
L_nE, L_Ne, L_NE                   = linechars[26], linechars[27], linechars[28]
L_nW, L_Nw, L_NW                   = linechars[30], linechars[31], linechars[32]
L_nEs, L_NeS, L_NES                = linechars[34], linechars[35], linechars[36]
L_nsW, L_NSw, L_NSW                = linechars[38], linechars[39], linechars[40]
L_EsW, L_eSw, L_ESW                = linechars[42], linechars[43], linechars[44]
L_nEW, L_New, L_NEW                = linechars[46], linechars[47], linechars[48]
L_nEsW, L_NeSw, L_NESW             = linechars[50], linechars[51], linechars[52]
C_es, C_sw, C_nw, C_ne             = linechars[54], linechars[55], linechars[56], linechars[57]# }}}

@dataclass(slots = True, frozen = True)
class Key:
    """Class representing user input keys"""
    ch: str
    _: KW_ONLY
    ctrl: bool = False
    alt: bool = False
    special: bool = False

@dataclass(slots = True)
class PadView:
    """Class representing a view of a curses pad window and the corresponding
    data that needs to be tracked when drawing pads"""
    pad: curses.window
    pad_start: tuple[int,int] = (0, 0)
    desired_screen_start: tuple[int,int] = (0, 0)
    desired_view_size: tuple[int,int] = (0, 0)

@dataclass(slots = True)
class WindowDrawState:
    """Class representing a window and its corresponding drawing callback
    function"""
    win: curses.window
    on_draw: Callable[[curses.window], bool] | None = None

@dataclass(slots = True)
class Cursor:
    """Class representing the position of the cursor on the screen"""
    cursor: tuple[int, int]

ChildWindow = tuple[WindowDrawState, PadView | None]

KeyMap = OrderedDict[Key, Callable[[], None]]

@dataclass
class BaseEvent:
    """Base class for specifying events; sub-class this to add custom messages
    to an application"""
    ...

class EventHandler:
    """Handler for processing application events"""
    __slots__ = ("callbacks", "queue")

    def __init__(self):# {{{
        self.callbacks: OrderedDict[type, Callable[[BaseEvent], None]] = OrderedDict()
        self.queue: list[BaseEvent] = [] # }}}

    def bind(self, event_t: type, callback: Callable[[BaseEvent], None]) -> bool:# {{{
        """Bind event type to callback

        event_t must be a subclass of BaseEvent

        Returns False is type is already bound"""
        assert issubclass(event_t, BaseEvent)
        if event_t in self.callbacks:
            return False
        self.callbacks[event_t] = callback
        return True # }}}

    def rebind(self,# {{{
               event_t: type,
               callback: Callable[[BaseEvent], None]) -> Callable[[BaseEvent], None] | None:
        """Force binding event type to callback

        event_t must be a subclass of BaseEvent

        Return previously bound callback or None"""
        assert issubclass(event_t, BaseEvent)
        previous_callback: Callable[[BaseEvent], None] | None
        if event_t in self.callbacks:
            previous_callback = self.callbacks[event_t]
            self.callbacks[event_t] = callback
        else:
            previous_callback = None
        return previous_callback # }}}

    def enqueue(self, event: BaseEvent) -> bool:# {{{
        """Enqueue event"""
        self.queue.append(event) # }}}

    def process(self):# {{{
        """Process event queue"""
        while len(self.queue) > 0:
            event = self.queue.pop(0)
            if type(event) not in self.callbacks:
                # weird scenario where the bound callback got removed before the
                # event was processed; intention in removing the callback
                # means ignore this event
                continue
            callback = self.callbacks[type(event)]
            callback(event) # }}}

# TODO pylint says: R0902 too-many-instance-attributes
class MainWindow:
    """Permits forwarding arguments via MainWindow.forwarding_args.

    See start_curses for more information."""
    __slots__ = ("_stdscr", "children", "keymap", "is_running", "_getkbytes", "stdcurs",
                 "on_post_key", "forwarding_args")

    def __init__(self,# {{{
                 stdscr_: curses.window,
                 *args,
                 nodelay: bool = False,
                 on_post_key: Callable[[], None] | None = None,
                 **kwargs):
        self._stdscr = stdscr_
        self.children: list[ChildWindow] = []
        self.keymap: KeyMap = OrderedDict()
        self.is_running = False
        self.stdcurs = Cursor((0, 0))
        self.on_post_key = on_post_key

        self.forwarding_args = (args, kwargs)

        if nodelay:
            curses.nodelay()
            self._getkbytes = getkbytes
        else:
            self._getkbytes = getkbytes_blocking# }}}

    @property
    def stdscr(self) -> curses.window:# {{{
        """The curses window corresponding to the physical screen"""
        return self._stdscr# }}}

    @property
    def stddraw(self) -> WindowDrawState:# {{{
        """The bundled drawing context of the main window"""
        return WindowDrawState(self.stdscr, self.on_draw)# }}}

    def on_draw(self, _) -> bool:# {{{
        """Callback for drawing"""
        self.stdscr.erase()
        self.stdscr.noutrefresh()
        for child in self.children:
            windraw_noutrefresh(*child)

        self.move_cursor(self.stdcurs)
        return False# }}}

    def move_cursor(self, cursor: Cursor):# {{{
        """Move the screen cursor to the specified cursor position"""
        win_move_cursor(self._stdscr, cursor)# }}}

    def add_child(self, windraw: WindowDrawState, pv: PadView | None = None):# {{{
        """Add a child to the main window draw stack"""
        self.children.append((windraw, pv))# }}}

    def add_mapping(self, key: Key, callback: Callable[[], None]) -> bool:# {{{
        '''Return False if the key is already assigned, in which case, remove
        the existing mapping and add the new one; otherwise return True'''
        if key in self.keymap:
            return False
        self.keymap[key] = callback
        return True# }}}

    def remove_mapping(self, key: Key) -> Callable[[], None] | None:# {{{
        '''Return callback if key was removed, otherwise None'''
        if key not in self.keymap:
            return None
        callback = self.keymap[key]
        del self.keymap[key]
        return callback# }}}

    def refresh(self):# {{{
        """Refresh the main window"""
        windraw_refresh(self.stddraw)# }}}

    def quit(self):# {{{
        """Quit the mainloop"""
        self.is_running = False# }}}

    def mainloop(self):# {{{
        """Run the application mainloop

        Note that this may raise KeyboardInterrupt in certain terminal modes."""
        self.is_running = True
        while self.is_running:
            kbytes = self._getkbytes(self._stdscr)
            key = key_from_bytes(kbytes)
            if key is None:
                continue
            for mapped in self.keymap:
                if key == mapped:
                    self.keymap[key]()
                    break

            if self.on_post_key is not None:
                self.on_post_key()# }}}

@dataclass(slots = True)
class DisplayRestore:
    """Class representing a restore point for MainWindow.

    See create_display_restore and restore_display"""
    stdwin: MainWindow
    keymap: KeyMap
    windraw: WindowDrawState
    pv: PadView
    post_restore: Callable[[], None]

def padview_clamp(pv: PadView) -> tuple[int,int,int,int,int,int]:# {{{
    '''Provides clamped values for pv.refresh() or pv.noutrefresh()'''
    py, px = pv.pad_start
    sy, sx = pv.desired_screen_start
    h, w = pv.desired_view_size
    pmaxy, pmaxx = pv.pad.getmaxyx()
    smaxy = curses.LINES - 1
    smaxx = curses.COLS - 1

    py = clamp(py, pmaxy, 0)
    px = clamp(px, pmaxx, 0)
    h = clamp(clamp(h, pmaxy - py), smaxy)
    w = clamp(clamp(w, pmaxx - px), smaxx)
    sy = clamp(sy, smaxy - h)
    sx = clamp(sx, smaxx - w)
    return py, px, sy, sx, sy + h, sx + w# }}}

def windraw_noutrefresh(windraw: WindowDrawState, pv: PadView | None = None):# {{{
    """Invoke drawing callback but hold off on refreshing the screen"""
    assert pv is None or id(windraw.win) == id(pv.pad)
    dorefresh = windraw.on_draw(windraw.win) if windraw.on_draw is not None else True
    if pv is None and dorefresh:
        windraw.win.noutrefresh()
    elif dorefresh:
        windraw.win.noutrefresh(*padview_clamp(pv)) # }}}

def windraw_refresh(windraw: WindowDrawState, pv: PadView | None = None):# {{{
    """Invoke drawing callback and refresh the screen"""
    curses.update_lines_cols()
    windraw_noutrefresh(windraw, pv)
    curses.doupdate()# }}}

def utf8_len(byte0: int) -> int:# {{{
    '''Return the expected length of a UTF-8 code point in bytes given the first byte

    Note: this function does not decode the code point, nor does it check if the first
    byte is valid; it just naively checks value ranges in the most significant four bits'''
    assert 0 <= byte0 < 0x100
    if byte0 < 0x80:
        return 1
    if byte0 < 0xe0:
        return 2
    if byte0 < 0xf0:
        return 3
    return 4# }}}

IDLE_KEY_NAME = "IDLE"
IDLE_KEY = Key(IDLE_KEY_NAME, special = True)

def getkbytes(win: curses.window) -> list[int]:# {{{
    """Fetch next keyboard bytes from user typeahead"""
    kbytes = []
    key = win.getch()
    kbytes.append(key)
    while key != -1:
        key = win.getch()
        kbytes.append(key)
    return kbytes# }}}

def getkbytes_blocking(win: curses.window) -> list[int]:# {{{
    """Fetch next keyboard bytes from user with blocking call"""
    byte0 = win.getch()
    assert byte0 < curses.KEY_MAX
    if byte0 == -1:
        return [byte0] # this can happen when halfdelay mode is set
    if byte0 >= curses.KEY_MIN:
        return [byte0]
    if byte0 == cascii.ESC:
        return [byte0] + getkbytes_blocking(win)

    kbytes = [byte0]
    i = utf8_len(byte0) - 1
    while i > 0:
        kbytes.append(win.getch())
        i -= 1
    return kbytes # }}}

def unctrl(byte: int) -> str:# {{{
    '''Unwraps curses' '^C' to 'C'; used for constructing Key objects'''
    return cascii.unctrl(byte)[1] # }}}

def key_from_bytes(xs: list[int]) -> Key | None:# {{{
    """Convert raw keyboard bytes to a known Key object, or None if a valid key
    could not be processed from the input bytes"""
    assert len(xs) > 0
    x = xs[0]
    xs = xs[:-1] if xs[-1] == -1 else xs

    result: Key | None = None
    if x == -1:
        result = IDLE_KEY
    if x >= curses.KEY_MIN and len(xs) == 1:
        result = Key(curses.keyname(x), special = True)
    if x > 0x80:
        try:
            result = Key(bytes(xs).decode("utf-8"))
        except UnicodeDecodeError:
            # could log, but I don't currently have a mechanism for that TODO maybe ???
            result = None
    if x == cascii.ESC and cascii.isctrl(xs[1]):
        result = Key(unctrl(xs[1]), ctrl = True, alt = True)
    if x == cascii.ESC:
        result = Key(chr(xs[1]), alt = True)
    if cascii.isctrl(x):
        result = Key(unctrl(x), ctrl = True)
    else:
        result = Key(chr(x))

    return result # }}}

SPECIAL_KEYS = tuple(m for m in dir(curses) if m.startswith("KEY_"))

def askey(ch: str) -> Key:# {{{
    """Represent unicode character as a user key input"""
    if ch == IDLE_KEY_NAME:
        return IDLE_KEY
    if ch in SPECIAL_KEYS:
        return Key(curses.keyname(getattr(curses, ch)), special = True)
    if ch.startswith("KEY_"):
        raise ValueError(f"Unknown key type: {ch}")

    upper = ch.upper()
    c_m = upper.startswith("C-M-")
    m_c = upper.startswith("M-C-")
    if c_m or m_c:
        return Key(upper[4], ctrl = True, alt = True)
    if upper.startswith("C-"):
        return Key(upper[2], ctrl = True)
    if upper.startswith("M-"):
        return Key(ch[2], alt = True)
    return Key(ch) # }}}

def win_addlines(win: curses.window, lines: list[str], y: int = 0, x: int = 0):# {{{
    """Add lines to curses window"""
    maxy, maxx = win.getmaxyx()
    for line in lines:
        win.addstr(y, x, line[:maxx + x + 1])
        y += 1
        if y > maxy:
            break # }}}

def win_move_cursor(win: curses.window, cursor: Cursor):# {{{
    """Move screen cursor to specified cursor position relative to the
    specified window"""
    cy, cx = cursor.cursor
    if cy < 0 or cy > curses.LINES - 1 or cx < 0 or cx > curses.COLS - 1:
        curses.curs_set(0)
    else:
        curses.curs_set(1)
        win.move(cy, cx) # }}}

def create_display_restore(# {{{
        stdwin: MainWindow,
        windraw: WindowDrawState,
        pv: PadView,
        post_restore: Callable[[], None]) -> DisplayRestore:
    """Create a restore point for a MainWindow"""
    return DisplayRestore(
            stdwin,
            stdwin.keymap,
            windraw,
            pv,
            post_restore)# }}}

def restore_display(dp: DisplayRestore):# {{{
    """Restore display from restore point"""
    dp.stdwin.keymap = dp.keymap
    dp.windraw.on_draw = None
    dp.pv.desired_view_size = (0, 0)
    dp.pv.desired_screen_start = (0, 0)
    dp.post_restore()
    dp.stdwin.refresh()# }}}

def start_curses(# {{{
        stdscr: curses.window,
        init_fn: Callable[[curses.window], None],
        main_fn: Callable[[MainWindow], T],
        *args,
        **kwargs) -> T:
    """Initialise curses context and calls a main function with a constructed
    MainWindow object. Any optional arguments passed to the MainWindow
    constructor are forwarded to the main function via the forwarding_args
    mechanism. Refer to MainWindow to see what keynames are consumed by its
    constructor."""
    init_fn(stdscr)
    stdwin = MainWindow(stdscr, *args, **kwargs)
    args, kwargs = stdwin.forwarding_args
    return main_fn(stdwin, *args, **kwargs)# }}}

# vim: foldmethod=marker
