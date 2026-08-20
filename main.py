#!/usr/bin/env python3

import curses

import tui

class BaseEvent:
    pass

class QuitEvent(BaseEvent):
    pass

class MinesweeperApp:
    def __init__(self, stdwin: tui.MainWindow):# {{{
        self.stdwin = stdwin
        self.grid_size = (10,10)
        self.mines = 30
        # TODO
        #self.grid = generate_grid(self.grid_size, self.mines)
        self.data = {}

        # TODO
        #self.event_queue: list[BaseEvent] = []
        #self.stdwin.on_post_key = self.on_post_key

        # TODO
        #self.init_gameview()
        #self.init_information()
        self.init_overlay()
        self.init_titlebar()
        #self.init_statusbar()
        self.init_debug()

        # TODO set debug value

        self.stdwin.stdcurs.cursor = (-1, -1)
        self.stdwin.refresh()

        self.map_window()
        self.stdwin.mainloop()
# }}}
    def init_overlay(self):# {{{
        self.overlay_win = curses.newpad(100, 100)
        self.overlay_vw = tui.PadView(self.overlay_win, (0, 0), (0, 0), (0, 0))
        self.overlay = tui.WindowDrawState(self.overlay_win)
        self.stdwin.add_child(self.overlay, self.overlay_vw)
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

if __name__ == "__main__":
    curses.wrapper(tui.start_curses, init_curses, MinesweeperApp)

# vim: foldmethod=marker
