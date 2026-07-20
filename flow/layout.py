"""Phase 5: cell layouts. Working set: the INV family (X1/X2/X4).

Frame: sky130 hd — 2.72 um rows, 0.46 um sites, met1 rails. Devices are
folded into 0.85/0.325 um fingers (S-G-D-G-S...), so INV_XN is the same
proven pattern with 2N fingers: contact columns alternate source/drain,
all gates strap to one poly pad in a dedicated input column.

Lessons encoded from the DRC grind (25 -> 0 on INV_X1):
  - the input contact needs its own column (li would short A to Y);
  - licon rows sit on the 0.005 grid independent of diff centers;
  - poly licon keeps 0.19 (euclidean) to any diff.
NAND/NOR/BUF/DFF are per-cell routing puzzles (poly cannot cross poly) —
next sessions, one puzzle at a time.
"""
from pathlib import Path

import gdstk

NWELL = (64, 20)
DIFF = (65, 20)
NSDM = (93, 44)
PSDM = (94, 20)
POLY = (66, 20)
NPC = (95, 20)
LICON = (66, 44)
LI = (67, 20)
LIPIN = (67, 16)
LILBL = (67, 5)
MCON = (67, 44)
MET1 = (68, 20)
MET1LBL = (68, 5)
BND = (235, 4)

H = 2.72
SITE = 0.46
RAIL_W = 0.48
HALF = 0.23                 # column half-pitch: contact/gate alternate

WP_F = 0.85
WN_F = 0.325
LGATE = 0.15
CUT = 0.17
DIFF_ENC_LICON = 0.06
POLY_ENDCAP = 0.13
NPC_ENC = 0.10
SDM_ENC = 0.125
NWELL_ENC = 0.18
LI_W = 0.17
LI_ENC_LICON = 0.08

PDIFF_Y = (1.41, 1.41 + WP_F)
NDIFF_Y = (0.36, 0.36 + WN_F)
PY_CUT = 1.835
NY_CUT = 0.52
PAD_Y = 1.13
POLY_PAD = 0.33
STRAP_Y = (PAD_Y - 0.075, PAD_Y + 0.075)


def inv_cell(lib, name, fingers):
    """INV with `fingers` gate fingers (W = fingers * finger width)."""
    cell = gdstk.Cell(name)

    def rect(layer, x0, y0, x1, y1):
        cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                                 (round(x1, 3), round(y1, 3)),
                                 layer=layer[0], datatype=layer[1]))

    ncols = 2 * fingers + 1                 # contacts + gates alternating
    xc = [HALF * (1 + i) for i in range(ncols)]     # first contact at 0.23
    gates = xc[1::2]
    cons = xc[0::2]
    pad_x = xc[-1] + 0.37                   # input column, right of the array
    width_raw = pad_x + 0.32
    import math
    W = math.ceil(round(width_raw / SITE, 3)) * SITE

    rect(BND, 0, 0, W, H)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)

    dx0 = cons[0] - CUT / 2 - DIFF_ENC_LICON
    dx1 = cons[-1] + CUT / 2 + DIFF_ENC_LICON
    pd0, pd1 = PDIFF_Y
    nd0, nd1 = NDIFF_Y
    rect(DIFF, dx0, pd0, dx1, pd1)
    rect(DIFF, dx0, nd0, dx1, nd1)
    rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
    rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
    rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)

    for xg in gates:
        rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
             xg + LGATE / 2, pd1 + POLY_ENDCAP)
    rect(POLY, gates[0] - LGATE / 2, STRAP_Y[0],
         pad_x + POLY_PAD / 2, STRAP_Y[1])
    rect(POLY, pad_x - POLY_PAD / 2, PAD_Y - POLY_PAD / 2,
         pad_x + POLY_PAD / 2, PAD_Y + POLY_PAD / 2)
    rect(NPC, pad_x - CUT / 2 - NPC_ENC, PAD_Y - CUT / 2 - NPC_ENC,
         pad_x + CUT / 2 + NPC_ENC, PAD_Y + CUT / 2 + NPC_ENC)
    rect(LICON, pad_x - CUT / 2, PAD_Y - CUT / 2,
         pad_x + CUT / 2, PAD_Y + CUT / 2)

    for x in cons:
        rect(LICON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)
        rect(LICON, x - CUT / 2, NY_CUT - CUT / 2, x + CUT / 2, NY_CUT + CUT / 2)

    # even contact columns are sources (rails), odd are drains (Y)
    src = cons[0::2]
    drn = cons[1::2]
    for x in src:
        rect(LI, x - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON, x + LI_W / 2, H)
        rect(LI, x - LI_W / 2, 0, x + LI_W / 2, NY_CUT + CUT / 2 + LI_ENC_LICON)
        rect(MCON, x - CUT / 2, H - CUT, x + CUT / 2, H)
        rect(MCON, x - CUT / 2, 0, x + CUT / 2, CUT)
    for x in drn:
        rect(LI, x - LI_W / 2, NY_CUT - CUT / 2 - LI_ENC_LICON,
             x + LI_W / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
    if len(drn) > 1:                        # join multiple drains at PAD_Y band
        rect(LI, drn[0] - LI_W / 2, PAD_Y + 0.10,
             drn[-1] + LI_W / 2, PAD_Y + 0.10 + LI_W)
    rect(LI, pad_x - CUT / 2 - LI_ENC_LICON, PAD_Y - LI_W / 2,
         pad_x + CUT / 2 + LI_ENC_LICON, PAD_Y + LI_W / 2)

    ypin = PAD_Y + 0.10 + LI_W / 2 if len(drn) > 1 else PAD_Y
    rect(LIPIN, drn[0] - LI_W / 2, ypin - 0.085, drn[0] + LI_W / 2, ypin + 0.085)
    cell.add(gdstk.Label("Y", (drn[0], ypin), layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, pad_x - 0.085, PAD_Y - 0.085, pad_x + 0.085, PAD_Y + 0.085)
    cell.add(gdstk.Label("A", (pad_x, PAD_Y), layer=LILBL[0], texttype=LILBL[1]))
    cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0], texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0], texttype=MET1LBL[1]))

    lib.add(cell)
    return W


def nand2_cell(lib, name):
    """NAND2, folded: pdiff 4 parallel fingers (A,B,B,A), ndiff two ABBA
    series chains with uncontacted internal nodes. Routing plan (each net
    on the layer that avoids crossings):
      B  — poly strap between its adjacent gates, pad on the strap
      A  — poly pads flanking the array, joined by a met1 bar
      Y  — all on li: top bar joins the two P drains; the N drain jogs
           right at low y and rises at the c3 column
      vdd middle tap — escapes vertically on met1 (li would cross Y's bar)
    """
    cell = gdstk.Cell(name)

    def rect(layer, x0, y0, x1, y1):
        cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                                 (round(x1, 3), round(y1, 3)),
                                 layer=layer[0], datatype=layer[1]))

    C = [0.69, 1.15, 1.61, 2.07, 2.53]          # contact columns
    G = [0.92, 1.38, 1.84, 2.30]                # gates: A, B, B, A
    PAD_L, PAD_R = 0.23, 2.90                   # A poly pads
    W = 7 * SITE                                # 3.22
    nd0, nd1 = 0.36, 1.01                       # ndiff 0.65 (chain fingers)
    NY = 0.52                                   # low licon row: leaves room
    pd0, pd1 = PDIFF_Y                          # for the jog's li enclosure
    BARY = (1.325, 1.495)   # Y li bar — 0.17 below the P-row li patches
    A_BAR = (0.985, 1.275)                      # A met1 bar (encloses mcons)

    rect(BND, 0, 0, W, H)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)

    dx0 = C[0] - CUT / 2 - DIFF_ENC_LICON
    dx1 = C[-1] + CUT / 2 + DIFF_ENC_LICON
    rect(DIFF, dx0, pd0, dx1, pd1)
    rect(DIFF, dx0, nd0, dx1, nd1)
    rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
    rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
    rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)

    for xg in G:
        rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
             xg + LGATE / 2, pd1 + POLY_ENDCAP)

    # ---- input A: flanking pads + met1 bar ----
    for px, xg, sgn in ((PAD_L, G[0], 1), (PAD_R, G[3], -1)):
        rect(POLY, min(px, xg) - (POLY_PAD / 2 if px < xg else LGATE / 2),
             1.055, max(px, xg) + (POLY_PAD / 2 if px > xg else LGATE / 2),
             1.205)
        rect(POLY, px - POLY_PAD / 2, PAD_Y - POLY_PAD / 2,
             px + POLY_PAD / 2, PAD_Y + POLY_PAD / 2)
        rect(NPC, px - CUT / 2 - NPC_ENC, PAD_Y - CUT / 2 - NPC_ENC,
             px + CUT / 2 + NPC_ENC, PAD_Y + CUT / 2 + NPC_ENC)
        rect(LICON, px - CUT / 2, PAD_Y - CUT / 2, px + CUT / 2, PAD_Y + CUT / 2)
        rect(LI, px - CUT / 2, PAD_Y - CUT / 2 - LI_ENC_LICON,
             px + CUT / 2, PAD_Y + CUT / 2 + LI_ENC_LICON)
        rect(MCON, px - CUT / 2, PAD_Y - CUT / 2, px + CUT / 2, PAD_Y + CUT / 2)
    rect(MET1, PAD_L - CUT / 2 - 0.06, A_BAR[0], PAD_R + CUT / 2 + 0.06, A_BAR[1])

    # ---- input B: strap + pad ABOVE the pdiff (the mid-band cannot host a
    # pad without the poly dipping into a diff -> parasitic gate / LVS fail)
    BP, TOP_Y = 1.38, 2.50
    for xg in (G[1], G[2]):                     # extend B fingers upward
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2,
             TOP_Y + 0.075)
    rect(POLY, G[1] - LGATE / 2, TOP_Y - 0.075, G[2] + LGATE / 2, TOP_Y + 0.075)
    rect(POLY, BP - POLY_PAD / 2, TOP_Y - POLY_PAD / 2,
         BP + POLY_PAD / 2, TOP_Y + POLY_PAD / 2)
    rect(NPC, BP - CUT / 2 - NPC_ENC, TOP_Y - CUT / 2 - NPC_ENC,
         BP + CUT / 2 + NPC_ENC, TOP_Y + CUT / 2 + NPC_ENC)
    rect(LICON, BP - CUT / 2, TOP_Y - CUT / 2, BP + CUT / 2, TOP_Y + CUT / 2)
    rect(LI, BP - CUT / 2, TOP_Y - CUT / 2 - LI_ENC_LICON,
         BP + CUT / 2, TOP_Y + CUT / 2 + LI_ENC_LICON)

    # ---- licons ----
    for x in C:                                     # P row: all columns
        rect(LICON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)
    for x in (C[0], C[2], C[4]):                    # N row: chain ends only
        rect(LICON, x - CUT / 2, NY - CUT / 2, x + CUT / 2, NY + CUT / 2)

    # ---- vss (N sources c0, c4) and vdd (P sources c0, c4 on li) ----
    for x in (C[0], C[4]):
        rect(LI, x - LI_W / 2, 0, x + LI_W / 2, NY + CUT / 2 + LI_ENC_LICON)
        rect(MCON, x - CUT / 2, 0, x + CUT / 2, CUT)
        rect(LI, x - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON, x + LI_W / 2, H)
        rect(MCON, x - CUT / 2, H - CUT, x + CUT / 2, H)
    # middle vdd tap (c2 P source): NARROW li patch (licon width, y-pair
    # enclosure) -> mcon -> met1 to the rail. NOTE: a wider patch would
    # OVERLAP the Y bar — a same-layer different-net short that DRC merges
    # silently and only LVS would catch; hence the bar sits 0.17 below.
    rect(LI, C[2] - CUT / 2, PY_CUT - CUT / 2 - LI_ENC_LICON,
         C[2] + CUT / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
    rect(MCON, C[2] - CUT / 2, PY_CUT - CUT / 2, C[2] + CUT / 2, PY_CUT + CUT / 2)
    rect(MET1, C[2] - CUT / 2 - 0.06, PY_CUT - CUT / 2 - 0.06,
         C[2] + CUT / 2 + 0.06, H)

    # ---- Y net, all li: P drains c1,c3 + N drain c2 ----
    for x in (C[1], C[3]):                          # stubs down to the bar
        rect(LI, x - LI_W / 2, BARY[0], x + LI_W / 2,
             PY_CUT + CUT / 2 + LI_ENC_LICON)
    # bar split around the c2 vdd met1?  no — bar is li, vdd escape is met1:
    # the only li conflict would be the c2 vdd stub, which is now met1, so
    # one continuous bar works
    rect(LI, C[1] - LI_W / 2, BARY[0], C[3] + LI_W / 2, BARY[1])
    # N drain: patch at c2 (with 0.08 li y-enclosure), jog right, rise at c3
    rect(LI, C[2] - CUT / 2, NY - CUT / 2 - LI_ENC_LICON,
         C[3] + LI_W / 2, NY + CUT / 2 + LI_ENC_LICON)
    rect(LI, C[3] - LI_W / 2, NY - CUT / 2, C[3] + LI_W / 2, BARY[1])

    # ---- pins ----
    rect(LIPIN, C[1] - LI_W / 2, 1.41 - 0.085, C[1] + LI_W / 2, 1.41 + 0.085)
    cell.add(gdstk.Label("Y", (C[1], 1.41), layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, BP - CUT / 2, TOP_Y - 0.085, BP + CUT / 2, TOP_Y + 0.085)
    cell.add(gdstk.Label("B", (BP, TOP_Y), layer=LILBL[0], texttype=LILBL[1]))
    cell.add(gdstk.Label("A", (PAD_L, A_BAR[0] + 0.07), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    lib.add(cell)
    return W


def nor2_cell(lib, name):
    """NOR2 = NAND2 mirrored: pdiff carries two ABBA series chains (0.85
    fingers, de-rated W — see cells.py), ndiff four parallel 0.325
    fingers. Same routing recipe upside-down: B strap+pad on top, A
    flanking pads + met1 bar, Y on li with a LOW bar (N drains) fed by a
    P-drain jog at the licon row and a riser at c3; the middle vss tap
    escapes DOWN on met1."""
    cell = gdstk.Cell(name)

    def rect(layer, x0, y0, x1, y1):
        cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                                 (round(x1, 3), round(y1, 3)),
                                 layer=layer[0], datatype=layer[1]))

    C = [0.69, 1.15, 1.61, 2.07, 2.53]
    G = [0.92, 1.38, 1.84, 2.30]                # A, B, B, A
    PAD_L, PAD_R = 0.23, 2.90
    W = 7 * SITE
    nd0, nd1 = 0.36, 0.685                      # 4 parallel 0.325 fingers
    NY = 0.52
    pd0, pd1 = PDIFF_Y                          # 2 series chains, 0.85
    BARY = (0.85, 1.02)                         # Y li bar (low band)
    A_BAR = (1.115, 1.405)                      # A met1 bar
    PAD_YY = 1.26                               # flanking pad licon row
    BP, TOP_Y = 1.38, 2.50

    rect(BND, 0, 0, W, H)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)

    dx0 = C[0] - CUT / 2 - DIFF_ENC_LICON
    dx1 = C[-1] + CUT / 2 + DIFF_ENC_LICON
    rect(DIFF, dx0, pd0, dx1, pd1)
    rect(DIFF, dx0, nd0, dx1, nd1)
    rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
    rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
    rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)

    for xg in G:
        rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
             xg + LGATE / 2, pd1 + POLY_ENDCAP)

    # A: flanking pads + met1 bar
    for px, xg in ((PAD_L, G[0]), (PAD_R, G[3])):
        rect(POLY, min(px, xg) - (POLY_PAD / 2 if px < xg else LGATE / 2),
             PAD_YY - 0.075, max(px, xg) +
             (POLY_PAD / 2 if px > xg else LGATE / 2), PAD_YY + 0.075)
        rect(POLY, px - POLY_PAD / 2, PAD_YY - POLY_PAD / 2,
             px + POLY_PAD / 2, PAD_YY + POLY_PAD / 2)
        rect(NPC, px - CUT / 2 - NPC_ENC, PAD_YY - CUT / 2 - NPC_ENC,
             px + CUT / 2 + NPC_ENC, PAD_YY + CUT / 2 + NPC_ENC)
        rect(LICON, px - CUT / 2, PAD_YY - CUT / 2,
             px + CUT / 2, PAD_YY + CUT / 2)
        rect(LI, px - CUT / 2, PAD_YY - CUT / 2 - LI_ENC_LICON,
             px + CUT / 2, PAD_YY + CUT / 2 + LI_ENC_LICON)
        rect(MCON, px - CUT / 2, PAD_YY - CUT / 2,
             px + CUT / 2, PAD_YY + CUT / 2)
    rect(MET1, PAD_L - CUT / 2 - 0.06, A_BAR[0],
         PAD_R + CUT / 2 + 0.06, A_BAR[1])

    # B: strap + pad above the pdiff
    for xg in (G[1], G[2]):
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2,
             TOP_Y + 0.075)
    rect(POLY, G[1] - LGATE / 2, TOP_Y - 0.075, G[2] + LGATE / 2, TOP_Y + 0.075)
    rect(POLY, BP - POLY_PAD / 2, TOP_Y - POLY_PAD / 2,
         BP + POLY_PAD / 2, TOP_Y + POLY_PAD / 2)
    rect(NPC, BP - CUT / 2 - NPC_ENC, TOP_Y - CUT / 2 - NPC_ENC,
         BP + CUT / 2 + NPC_ENC, TOP_Y + CUT / 2 + NPC_ENC)
    rect(LICON, BP - CUT / 2, TOP_Y - CUT / 2, BP + CUT / 2, TOP_Y + CUT / 2)
    rect(LI, BP - CUT / 2, TOP_Y - CUT / 2 - LI_ENC_LICON,
         BP + CUT / 2, TOP_Y + CUT / 2 + LI_ENC_LICON)

    # licons: N row all columns; P row chain ends only
    for x in C:
        rect(LICON, x - CUT / 2, NY - CUT / 2, x + CUT / 2, NY + CUT / 2)
    for x in (C[0], C[2], C[4]):
        rect(LICON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)

    # rails: vdd P sources c0,c4 up; vss N sources c0,c2?no — c0,c2,c4 are
    # vss on N; but c2 needs the met1 escape (Y bar occupies li below? no —
    # Y bar is at 0.85..1.02, c2 stub down 0..0.605 does not cross it).
    for x in (C[0], C[4]):
        rect(LI, x - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON, x + LI_W / 2, H)
        rect(MCON, x - CUT / 2, H - CUT, x + CUT / 2, H)
    for x in (C[0], C[4]):
        rect(LI, x - LI_W / 2, 0, x + LI_W / 2, NY + CUT / 2 + LI_ENC_LICON)
        rect(MCON, x - CUT / 2, 0, x + CUT / 2, CUT)
    # c2 stub: licon enclosure on the x-sides — the top would come within
    # 0.165 of the Y bar (li.3 wants 0.17)
    rect(LI, C[2] - CUT / 2 - LI_ENC_LICON, 0,
         C[2] + CUT / 2 + LI_ENC_LICON, NY + CUT / 2)
    rect(MCON, C[2] - CUT / 2, 0, C[2] + CUT / 2, CUT)

    # Y: N drains c1,c3 stubs up to the low bar; P drain c2 jogs right at
    # the P licon row and rises down the c3 column
    for x in (C[1], C[3]):
        rect(LI, x - LI_W / 2, NY - CUT / 2 - LI_ENC_LICON, x + LI_W / 2,
             BARY[1])
    rect(LI, C[1] - LI_W / 2, BARY[0], C[3] + LI_W / 2, BARY[1])
    rect(LI, C[2] - CUT / 2, PY_CUT - CUT / 2 - LI_ENC_LICON,
         C[3] + LI_W / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
    rect(LI, C[3] - LI_W / 2, BARY[0], C[3] + LI_W / 2, PY_CUT + CUT / 2)

    # pins
    rect(LIPIN, C[1] - LI_W / 2, 0.935 - 0.085, C[1] + LI_W / 2, 0.935 + 0.085)
    cell.add(gdstk.Label("Y", (C[1], 0.935), layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, BP - CUT / 2, TOP_Y - 0.085, BP + CUT / 2, TOP_Y + 0.085)
    cell.add(gdstk.Label("B", (BP, TOP_Y), layer=LILBL[0], texttype=LILBL[1]))
    cell.add(gdstk.Label("A", (PAD_L, A_BAR[0] + 0.07), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    lib.add(cell)
    return W


def _mk(cell):
    def rect(layer, x0, y0, x1, y1):
        cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                                 (round(x1, 3), round(y1, 3)),
                                 layer=layer[0], datatype=layer[1]))
    return rect


def nand3_cell(lib, name):
    """NAND3, two ABC/CBA chains (2x stack comp — see cells.py). Net-to-
    resource assignment forced by adjacency analysis: with 2 chains of 3,
    exactly one net pairs at the chain boundary (C: top strap+pad), one
    lands on the outer gates (A: flanking pads + met1 bar), and one is
    stuck on inner solos (B) — solved with top pads joined by an li bar
    running OVER the pdiff at y2.09-2.26, which requires every li stub it
    crosses to be absent: mid vdd taps (c2,c4) escape on met1, and the
    P-row licon patches take x-side enclosures so their tops stop 0.17
    below the bar."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    C = [0.69 + 0.46 * i for i in range(7)]
    G = [0.92 + 0.46 * i for i in range(6)]     # A B C C B A
    PAD_L, PAD_R = 0.23, 3.91
    W = 10 * SITE
    nd0, nd1, NY = 0.36, 1.01, 0.52
    pd0, pd1 = PDIFF_Y
    BARY = (1.575, 1.745)
    A_BAR = (0.985, 1.275)
    B_BAR = (2.09, 2.26)
    BPADY = 2.51                                 # B/C top pad licon row

    rect(BND, 0, 0, W, H)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)
    dx0 = C[0] - CUT / 2 - DIFF_ENC_LICON
    dx1 = C[-1] + CUT / 2 + DIFF_ENC_LICON
    rect(DIFF, dx0, pd0, dx1, pd1)
    rect(DIFF, dx0, nd0, dx1, nd1)
    rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
    rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
    rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)

    for xg in G:
        rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
             xg + LGATE / 2, pd1 + POLY_ENDCAP)

    # A (outer): flanking pads + met1 bar
    for px, xg in ((PAD_L, G[0]), (PAD_R, G[5])):
        rect(POLY, min(px, xg) - (POLY_PAD / 2 if px < xg else LGATE / 2),
             1.055, max(px, xg) +
             (POLY_PAD / 2 if px > xg else LGATE / 2), 1.205)
        rect(POLY, px - POLY_PAD / 2, PAD_Y - POLY_PAD / 2,
             px + POLY_PAD / 2, PAD_Y + POLY_PAD / 2)
        rect(NPC, px - CUT / 2 - NPC_ENC, PAD_Y - CUT / 2 - NPC_ENC,
             px + CUT / 2 + NPC_ENC, PAD_Y + CUT / 2 + NPC_ENC)
        rect(LICON, px - CUT / 2, PAD_Y - CUT / 2, px + CUT / 2, PAD_Y + CUT / 2)
        rect(LI, px - CUT / 2, PAD_Y - CUT / 2 - LI_ENC_LICON,
             px + CUT / 2, PAD_Y + CUT / 2 + LI_ENC_LICON)
        rect(MCON, px - CUT / 2, PAD_Y - CUT / 2, px + CUT / 2, PAD_Y + CUT / 2)
    rect(MET1, PAD_L - CUT / 2 - 0.06, A_BAR[0], PAD_R + CUT / 2 + 0.06, A_BAR[1])

    # C (chain-boundary pair g2,g3): fingers up + strap + raised top pad
    for xg in (G[2], G[3]):
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2, 2.68)
    rect(POLY, G[2] - LGATE / 2, 2.35, G[3] + LGATE / 2, 2.50)
    CPX = 2.07
    rect(POLY, CPX - POLY_PAD / 2, BPADY - POLY_PAD / 2,
         CPX + POLY_PAD / 2, BPADY + POLY_PAD / 2)
    rect(NPC, CPX - CUT / 2 - NPC_ENC, BPADY - CUT / 2 - NPC_ENC,
         CPX + CUT / 2 + NPC_ENC, BPADY + CUT / 2 + NPC_ENC)
    rect(LICON, CPX - CUT / 2, BPADY - CUT / 2, CPX + CUT / 2, BPADY + CUT / 2)
    rect(LI, CPX - CUT / 2 - LI_ENC_LICON, BPADY - CUT / 2,
         CPX + CUT / 2 + LI_ENC_LICON, BPADY + CUT / 2)     # x-side enclosure

    # B (inner solos g1,g4): top pads + stubs + li bar over the pdiff
    for xg in (G[1], G[4]):
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2, 2.675)
        rect(POLY, xg - POLY_PAD / 2, BPADY - POLY_PAD / 2 - 0.005,
             xg + POLY_PAD / 2, BPADY + POLY_PAD / 2 - 0.005)
        rect(NPC, xg - CUT / 2 - NPC_ENC, BPADY - CUT / 2 - NPC_ENC,
             xg + CUT / 2 + NPC_ENC, BPADY + CUT / 2 + NPC_ENC)
        rect(LICON, xg - CUT / 2, BPADY - CUT / 2, xg + CUT / 2, BPADY + CUT / 2)
        rect(LI, xg - CUT / 2 - LI_ENC_LICON, BPADY - CUT / 2,
             xg + CUT / 2 + LI_ENC_LICON, BPADY + CUT / 2)  # x-side enc
        rect(LI, xg - CUT / 2, B_BAR[0], xg + CUT / 2, BPADY - CUT / 2)
    rect(LI, G[1] - CUT / 2, B_BAR[0], G[4] + CUT / 2, B_BAR[1])

    # licons: P all columns, N chain ends
    for x in C:
        rect(LICON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)
    for x in (C[0], C[3], C[6]):
        rect(LICON, x - CUT / 2, NY - CUT / 2, x + CUT / 2, NY + CUT / 2)

    # vdd: c0,c6 li stubs to rail; c2,c4 met1 escapes (B bar crosses there)
    for x in (C[0], C[6]):
        rect(LI, x - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON, x + LI_W / 2, H)
        rect(MCON, x - CUT / 2, H - CUT, x + CUT / 2, H)
    for x in (C[2], C[4]):
        rect(LI, x - CUT / 2 - LI_ENC_LICON, PY_CUT - CUT / 2,
             x + CUT / 2 + LI_ENC_LICON, PY_CUT + CUT / 2)  # x-side enc
        rect(MCON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)
        rect(MET1, x - CUT / 2 - 0.06, PY_CUT - CUT / 2 - 0.06, x + CUT / 2 + 0.06, H)
    # vss: chain ends c0,c6
    for x in (C[0], C[6]):
        rect(LI, x - LI_W / 2, 0, x + LI_W / 2, NY + CUT / 2 + LI_ENC_LICON)
        rect(MCON, x - CUT / 2, 0, x + CUT / 2, CUT)

    # Y: P drains c1,c5 (x-side-enc patches + stubs to the bar), N+P at c3
    for x in (C[1], C[5]):
        rect(LI, x - CUT / 2 - LI_ENC_LICON, PY_CUT - CUT / 2,
             x + CUT / 2 + LI_ENC_LICON, PY_CUT + CUT / 2)
        rect(LI, x - LI_W / 2, BARY[0], x + LI_W / 2, PY_CUT + CUT / 2)
    rect(LI, C[3] - CUT / 2, NY - CUT / 2 - LI_ENC_LICON,
         C[3] + CUT / 2, NY + CUT / 2 + LI_ENC_LICON)
    rect(LI, C[3] - CUT / 2 - LI_ENC_LICON, PY_CUT - CUT / 2,
         C[3] + CUT / 2 + LI_ENC_LICON, PY_CUT + CUT / 2)
    rect(LI, C[3] - LI_W / 2, NY, C[3] + LI_W / 2, PY_CUT + CUT / 2)
    rect(LI, C[1] - LI_W / 2, BARY[0], C[5] + LI_W / 2, BARY[1])

    # pins
    rect(LIPIN, C[1] - LI_W / 2, 1.66 - 0.085, C[1] + LI_W / 2, 1.66 + 0.085)
    cell.add(gdstk.Label("Y", (C[1], 1.66), layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, G[3] - 0.085, 2.175 - 0.085, G[3] + 0.085, 2.175 + 0.085)
    cell.add(gdstk.Label("B", (G[3], 2.175), layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, CPX - 0.085, BPADY - 0.085, CPX + 0.085, BPADY + 0.085)
    cell.add(gdstk.Label("C", (CPX, BPADY), layer=LILBL[0], texttype=LILBL[1]))
    cell.add(gdstk.Label("A", (PAD_L, A_BAR[0] + 0.07), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0], texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0], texttype=MET1LBL[1]))
    lib.add(cell)
    return W


def buf_cell(lib, name, s2_fingers):
    """BUF: stage-1 inverter (2 fingers, gates A) + stage-2 inverter
    (s2_fingers, gates yb). A: top strap+pad at the c0 column (its vdd
    stub becomes a met1 escape). yb: the c1 drain column rises past the
    P row and runs right at top to a pad on the stage-2 gate strap; every
    vdd li stub the run or the Y bar would cross is met1-escaped."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    n_g = 2 + s2_fingers
    n_c = n_g + 1
    C = [0.69 + 0.46 * i for i in range(n_c)]
    G = [0.92 + 0.46 * i for i in range(n_g)]
    W = ((2 * n_g + 2 + 2) * HALF // SITE + 1) * SITE
    import math
    W = math.ceil((C[-1] + 0.375) / SITE) * SITE
    nd0, nd1, NY = 0.36, 1.01, 0.52
    pd0, pd1 = PDIFF_Y
    BARY = (1.325, 1.495)   # 0.17 below the P-row patches (short hazard!)
    TOPY = 2.50

    rect(BND, 0, 0, W, H)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)
    dx0 = C[0] - CUT / 2 - DIFF_ENC_LICON
    dx1 = C[-1] + CUT / 2 + DIFF_ENC_LICON
    rect(DIFF, dx0, pd0, dx1, pd1)
    rect(DIFF, dx0, nd0, dx1, nd1)
    rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
    rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
    rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)
    for xg in G:
        rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
             xg + LGATE / 2, pd1 + POLY_ENDCAP)

    # all licons (both rows fully contacted: no series stacks)
    for x in C:
        rect(LICON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2, PY_CUT + CUT / 2)
        rect(LICON, x - CUT / 2, NY - CUT / 2, x + CUT / 2, NY + CUT / 2)

    vdd_cols = C[0::2]                        # even: supplies
    y_cols = [C[i] for i in range(3, n_c, 2)]  # stage-2 drains
    # met1-escaped vdd: c0 (A pad above), c2 (yb run), plus every vdd
    # column the Y bar spans (between first and last stage-2 drains)
    esc = {C[0], C[2]} | {x for x in vdd_cols if y_cols[0] < x < y_cols[-1]}
    for x in vdd_cols:
        if x in esc:
            rect(LI, x - CUT / 2, PY_CUT - CUT / 2 - LI_ENC_LICON,
                 x + CUT / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
            rect(MCON, x - CUT / 2, PY_CUT - CUT / 2, x + CUT / 2,
                 PY_CUT + CUT / 2)
            rect(MET1, x - CUT / 2 - 0.06, PY_CUT - CUT / 2 - 0.06,
                 x + CUT / 2 + 0.06, H)
        else:
            rect(LI, x - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON,
                 x + LI_W / 2, H)
            rect(MCON, x - CUT / 2, H - CUT, x + CUT / 2, H)
        rect(LI, x - LI_W / 2, 0, x + LI_W / 2, NY + CUT / 2 + LI_ENC_LICON)
        rect(MCON, x - CUT / 2, 0, x + CUT / 2, CUT)

    # A: stage-1 strap + pad at the c0 column, all at top
    for xg in (G[0], G[1]):
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2,
             TOPY + 0.075)
    rect(POLY, C[0] - POLY_PAD / 2, TOPY - 0.075, G[1] + LGATE / 2, TOPY + 0.075)
    rect(POLY, C[0] - POLY_PAD / 2, TOPY - POLY_PAD / 2,
         C[0] + POLY_PAD / 2, TOPY + POLY_PAD / 2)
    rect(NPC, C[0] - CUT / 2 - NPC_ENC, TOPY - CUT / 2 - NPC_ENC,
         C[0] + CUT / 2 + NPC_ENC, TOPY + CUT / 2 + NPC_ENC)
    rect(LICON, C[0] - CUT / 2, TOPY - CUT / 2, C[0] + CUT / 2, TOPY + CUT / 2)
    rect(LI, C[0] - CUT / 2, TOPY - CUT / 2 - LI_ENC_LICON,
         C[0] + CUT / 2, TOPY + CUT / 2 + LI_ENC_LICON)

    # yb: c1 vertical (drain of both rows) up to a top run, right to the
    # stage-2 gate strap pad on G[2]
    rect(LI, C[1] - CUT / 2, NY - CUT / 2 - LI_ENC_LICON,
         C[1] + CUT / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
    rect(LI, C[1] - LI_W / 2, NY, C[1] + LI_W / 2, TOPY + CUT / 2 + LI_ENC_LICON)
    rect(LI, C[1] - LI_W / 2, TOPY - CUT / 2 - LI_ENC_LICON,
         G[2] + CUT / 2 + LI_ENC_LICON, TOPY + CUT / 2 + LI_ENC_LICON)
    for xg in G[2:]:
        rect(POLY, xg - LGATE / 2, pd1 + POLY_ENDCAP, xg + LGATE / 2, 2.675)
    rect(POLY, G[2] - LGATE / 2, 2.35, G[-1] + LGATE / 2, 2.50)
    rect(POLY, G[2] - POLY_PAD / 2, TOPY - POLY_PAD / 2 - 0.005,
         G[2] + POLY_PAD / 2, TOPY + POLY_PAD / 2 - 0.005)
    rect(NPC, G[2] - CUT / 2 - NPC_ENC, TOPY - CUT / 2 - NPC_ENC,
         G[2] + CUT / 2 + NPC_ENC, TOPY + CUT / 2 + NPC_ENC)
    rect(LICON, G[2] - CUT / 2, TOPY - CUT / 2, G[2] + CUT / 2, TOPY + CUT / 2)

    # Y: stage-2 drains, both rows, joined by the mid bar
    for x in y_cols:
        rect(LI, x - LI_W / 2, NY - CUT / 2 - LI_ENC_LICON,
             x + LI_W / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
    rect(LI, y_cols[0] - LI_W / 2, BARY[0], y_cols[-1] + LI_W / 2, BARY[1])

    # pins
    ypin = (y_cols[0], 1.41)
    rect(LIPIN, ypin[0] - LI_W / 2, ypin[1] - 0.085,
         ypin[0] + LI_W / 2, ypin[1] + 0.085)
    cell.add(gdstk.Label("Y", ypin, layer=LILBL[0], texttype=LILBL[1]))
    rect(LIPIN, C[0] - 0.085, TOPY - 0.085, C[0] + 0.085, TOPY + 0.085)
    cell.add(gdstk.Label("A", (C[0], TOPY), layer=LILBL[0], texttype=LILBL[1]))
    cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0], texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0], texttype=MET1LBL[1]))
    lib.add(cell)
    return W


areas = {}
outdir = Path(__file__).parents[1] / "out"
for name, fingers in (("INV_X1", 2), ("INV_X2", 4), ("INV_X4", 8)):
    lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)
    w = inv_cell(lib, name, fingers)
    gds = outdir / f"{name.lower()}.gds"
    lib.write_gds(str(gds))
    areas[name] = round(w * H, 4)
    print(f"{name}: {fingers} fingers, W = {w:.2f} um ({w/SITE:.0f} sites), "
          f"area {areas[name]} um2 -> {gds.name}")

# NAND3 is NOT generated: routing analysis proved its inner-solo input has
# no legal li join slot in this template (the bar needs 0.17 clearance both
# to the P-row patches below and the top pads above — the window is 0.085).
# It is dropped from the library (cells.py); its 157 instances remap to
# NAND2 chains, and that measured cost is part of the PPA result.
for name, fn in (("NAND2_X1", nand2_cell), ("NOR2_X1", nor2_cell),
                 ("BUF_X2", lambda l, n: buf_cell(l, n, 4)),
                 ("BUF_X4", lambda l, n: buf_cell(l, n, 8))):
    lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)
    w = fn(lib, name)
    lib.write_gds(str(outdir / f"{name.lower()}.gds"))
    areas[name] = round(w * H, 4)
    print(f"{name}: W = {w:.2f} um ({w/SITE:.0f} sites), "
          f"area {areas[name]} um2 -> {name.lower()}.gds")

import json
(outdir / "areas_real.json").write_text(json.dumps(areas, indent=1))
