"""File: terminal.py
Author: chrysplusplus
Date: 2026-08-30

Curses and color terminal support"""

import curses

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
    ATTR_YELLOW   = curses.color_pair(7)

# vim: foldmethod=indent foldnestmax=2 foldlevel=2
