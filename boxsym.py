"""File: boxsym.py
Author: chrysplusplus
Date: 2026-08-30

Collection of box symbols"""

__all__= ("L_ew", "L_ns",
          "L_es", "L_sw", "L_ne", "L_nw",
          "L_nes", "L_nsw", "L_esw", "L_new",
          "L_nesw",
          "L_EW", "L_NS",
          "L_Es", "L_eS", "L_ES",
          "L_sW", "L_Sw", "L_SW",
          "L_nE", "L_Ne", "L_NE",
          "L_nW", "L_Nw", "L_NW",
          "L_nEs", "L_NeS", "L_NES",
          "L_nsW", "L_NSw", "L_NSW",
          "L_EsW", "L_eSw", "L_ESW",
          "L_nEW", "L_New", "L_NEW",
          "L_nEsW", "L_NeSw", "L_NESW",
          "C_es", "C_sw", "C_nw", "C_ne")

_tbl_boxsym = [#      1    2    3    4    5
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
               "53", "╭", "╮", "╯", "╰" ]

L_ew, L_ns                 = _tbl_boxsym[1],  _tbl_boxsym[2]
L_es, L_sw, L_ne, L_nw     = _tbl_boxsym[4],  _tbl_boxsym[5],  _tbl_boxsym[6],  _tbl_boxsym[7]
L_nes, L_nsw, L_esw, L_new = _tbl_boxsym[9],  _tbl_boxsym[10], _tbl_boxsym[11], _tbl_boxsym[12]
L_nesw                     = _tbl_boxsym[13]
L_EW, L_NS                 = _tbl_boxsym[15], _tbl_boxsym[16]
L_Es, L_eS, L_ES           = _tbl_boxsym[18], _tbl_boxsym[19], _tbl_boxsym[20]
L_sW, L_Sw, L_SW           = _tbl_boxsym[22], _tbl_boxsym[23], _tbl_boxsym[24]
L_nE, L_Ne, L_NE           = _tbl_boxsym[26], _tbl_boxsym[27], _tbl_boxsym[28]
L_nW, L_Nw, L_NW           = _tbl_boxsym[30], _tbl_boxsym[31], _tbl_boxsym[32]
L_nEs, L_NeS, L_NES        = _tbl_boxsym[34], _tbl_boxsym[35], _tbl_boxsym[36]
L_nsW, L_NSw, L_NSW        = _tbl_boxsym[38], _tbl_boxsym[39], _tbl_boxsym[40]
L_EsW, L_eSw, L_ESW        = _tbl_boxsym[42], _tbl_boxsym[43], _tbl_boxsym[44]
L_nEW, L_New, L_NEW        = _tbl_boxsym[46], _tbl_boxsym[47], _tbl_boxsym[48]
L_nEsW, L_NeSw, L_NESW     = _tbl_boxsym[50], _tbl_boxsym[51], _tbl_boxsym[52]
C_es, C_sw, C_nw, C_ne     = _tbl_boxsym[54], _tbl_boxsym[55], _tbl_boxsym[56], _tbl_boxsym[57]

