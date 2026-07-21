"""Phase 5 v2: cell layouts on the hd single-finger architecture.

v1 (git tag v1-symmetric-drive) proved 7 cells DRC/LVS-clean with
symmetric-drive folded devices — and then detailed routing proved the
architecture wrong: fat folded PMOS closes the cell mid-band, so input
pins have no in-cell landing the router can reach (DRT-0073). v2 is the
fix: Wp=1.0/Wn=0.65 single-finger devices, which opens a ~0.6 um mid-band
(y 0.885..1.485) where EVERY pin lives, clear of both rail shadows.

The architecture (and where in doubt the exact dimensions) follows
sky130_fd_sc_hd (Apache-2.0) — studied from the PDK GDS, re-implemented
here generatively. The recurring motifs:
  - input pads: poly hooks off the gate into the mid-band (licon row
    y 1.075..1.245, li patch, pin label at y 1.19);
  - output: li fingers over the drain columns, necked to keep exactly
    0.17 to the pad patches while crossing the mid-band;
  - source columns: li stubs merged into full-width li rails (+ met1
    rails and mcons for the PDN);
  - stubs shorten and licon rows shift wherever a crossing net needs its
    0.17 — every such deviation below is copied from the proven cells.
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
AREAID_SC = (81, 4)      # areaid.standardc: magic relaxes in-cell rules
                         # (licon.11 contact-to-gate 0.055 -> 0.05) for
                         # marked standard-cell regions; hd cells all
                         # carry it. The KLayout deck reads but never
                         # uses it, so our KLayout signoff is unchanged.

H = 2.72
SITE = 0.46
RAIL_W = 0.48

NDIFF_Y = (0.235, 0.885)
PDIFF_Y = (1.485, 2.485)
POLY_Y = (0.105, 2.615)
HOOK_Y = (0.995, 1.325)          # poly pad band in the mid-band
NPC_Y = (0.975, 1.345)
PADCUT_Y = (1.075, 1.245)        # pad licon row
PIN_Y = (1.105, 1.275)           # lipin box; labels at y 1.19
NROWS = [(0.295, 0.465), (0.655, 0.825)]                    # diff licons, n
PROWS = [(1.575, 1.745), (1.915, 2.085), (2.255, 2.425)]    # diff licons, p


def _mk(cell):
    def rect(layer, x0, y0, x1, y1):
        cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                                 (round(x1, 3), round(y1, 3)),
                                 layer=layer[0], datatype=layer[1]))
    return rect


def frame(cell, rect, W):
    """Boundary, li+met1 rails, rail mcons, npc band, implants, nwell."""
    rect(BND, 0, 0, W, H)
    rect(AREAID_SC, 0, 0, W, H)
    rect(LI, 0, -0.085, W, 0.085)
    rect(LI, 0, H - 0.085, W, H + 0.085)
    rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
    rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)
    x = 0.23
    while x < W:
        rect(MCON, x - 0.085, -0.085, x + 0.085, 0.085)
        rect(MCON, x - 0.085, H - 0.085, x + 0.085, H + 0.085)
        x += SITE
    rect(NPC, 0, NPC_Y[0], W, NPC_Y[1])
    rect(NSDM, 0, -0.19, W, 1.015)
    rect(PSDM, 0, 1.355, W, H + 0.19)
    rect(NWELL, -0.19, 1.305, W + 0.19, H + 0.19)
    cell.add(gdstk.Label("VPWR", (0.23, H), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))
    cell.add(gdstk.Label("VGND", (0.23, 0), layer=MET1LBL[0],
                         texttype=MET1LBL[1]))


def licons(rect, xc, rows):
    for y0, y1 in rows:
        rect(LICON, xc - 0.085, y0, xc + 0.085, y1)


def pin(cell, rect, name, x, y=1.19):
    rect(LIPIN, x - 0.085, y - 0.085, x + 0.085, y + 0.085)
    cell.add(gdstk.Label(name, (x, y), layer=LILBL[0], texttype=LILBL[1]))


def inv_x1(lib, name):
    """One finger each. Gate hooks its pad LEFT over the source column;
    Y necks right of the pad (0.17 gap)."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 3 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.34, *_y(NDIFF_Y, 1.01))
    rect(DIFF, 0.34, *_y(PDIFF_Y, 1.01))
    rect(POLY, 0.6, POLY_Y[0], 0.75, POLY_Y[1])                 # gate
    rect(POLY, 0.32, HOOK_Y[0], 0.6, HOOK_Y[1])                 # pad hook
    rect(LICON, 0.4, PADCUT_Y[0], 0.57, PADCUT_Y[1])            # pad licon
    licons(rect, 0.465, [(0.315, 0.485), (0.655, 0.825)] + PROWS)  # source
    licons(rect, 0.885, [(0.315, 0.485), (0.655, 0.825)] + PROWS)  # drain
    rect(LI, 0.32, 1.075, 0.65, 1.315)                          # A patch
    rect(LI, 0.32, 0.005, 0.55, 0.905)                          # src -> VGND
    rect(LI, 0.34, 1.495, 0.55, 2.675)                          # src -> VPWR
    rect(LI, 0.72, 0.255, 1.05, 0.885)                          # Y lower
    rect(LI, 0.82, 0.885, 1.05, 1.485)                          # Y neck
    rect(LI, 0.72, 1.485, 1.05, 2.465)                          # Y upper
    pin(cell, rect, "A", 0.445)
    pin(cell, rect, "Y", 0.905)
    lib.add(cell)
    return W


def _y(band, x1):
    return band[0], x1, band[1]


def inv_multi(lib, name, fingers):
    """INV_X2/X4: S-G-D-G-S(-G-D-G-S) on a 0.42 gate pitch, all gates
    joined by a mid-band poly strap that hooks the pad at the left source
    column. Y = drain fingers + join bars above/below the mid-band + a
    right-edge riser carrying the pin (X4)."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    if fingers == 2:
        W = 3 * SITE
        rect(DIFF, 0.145, *_y(NDIFF_Y, 1.235))
        rect(DIFF, 0.145, *_y(PDIFF_Y, 1.235))
        for gx in (0.48, 0.90):
            rect(POLY, gx - 0.075, POLY_Y[0], gx + 0.075, POLY_Y[1])
        rect(POLY, 0.105, HOOK_Y[0], 0.975, HOOK_Y[1])          # strap+pad
        rect(LICON, 0.185, PADCUT_Y[0], 0.355, PADCUT_Y[1])
        for xc in (0.27, 0.69, 1.11):
            licons(rect, xc, NROWS + PROWS)
        rect(LI, 0.105, 1.075, 0.435, 1.325)                    # A patch
        rect(LI, 0.125, 0.085, 0.355, 0.905)                    # VGND stubs
        rect(LI, 1.025, 0.085, 1.235, 0.905)
        rect(LI, 0.125, 1.495, 0.355, 2.635)                    # VPWR stubs
        rect(LI, 1.025, 1.495, 1.235, 2.635)
        rect(LI, 0.525, 0.255, 0.855, 0.885)                    # Y
        rect(LI, 0.605, 0.885, 0.855, 1.485)
        rect(LI, 0.525, 1.485, 0.855, 2.465)
        pin(cell, rect, "A", 0.27)
        pin(cell, rect, "Y", 0.69)
    else:                                                       # 4 fingers
        W = 5 * SITE
        rect(DIFF, 0.185, *_y(NDIFF_Y, 2.115))
        rect(DIFF, 0.185, *_y(PDIFF_Y, 2.115))
        for gx in (0.52, 0.94, 1.36, 1.78):
            rect(POLY, gx - 0.075, POLY_Y[0], gx + 0.075, POLY_Y[1])
        rect(POLY, 0.105, HOOK_Y[0], 1.855, HOOK_Y[1])
        rect(LICON, 0.185, PADCUT_Y[0], 0.355, PADCUT_Y[1])
        # sources: stubs shorten to clear the Y bars -> fewer licon rows
        licons(rect, 0.31, [NROWS[0]] + PROWS)
        licons(rect, 1.15, [NROWS[0], PROWS[1], PROWS[2]])
        licons(rect, 1.99, [NROWS[0], PROWS[2]])
        for xc in (0.73, 1.57):                                 # drains
            licons(rect, xc, NROWS + PROWS)
        rect(LI, 0.105, 1.075, 1.735, 1.325)                    # A bar
        rect(LI, 0.13, 0.085, 0.395, 0.545)                     # VGND stubs
        rect(LI, 1.065, 0.085, 1.235, 0.545)
        rect(LI, 1.905, 0.085, 2.155, 0.55)
        rect(LI, 0.13, 1.495, 0.395, 2.635)                     # VPWR stubs
        rect(LI, 1.065, 1.835, 1.235, 2.635)
        rect(LI, 1.905, 2.175, 2.115, 2.635)
        rect(LI, 0.565, 0.255, 0.895, 0.905)                    # Y n-fingers
        rect(LI, 1.405, 0.255, 1.735, 0.905)
        rect(LI, 0.565, 0.725, 1.905, 0.905)                    # low bar
        rect(LI, 1.905, 0.725, 2.17, 1.685)                     # pin riser
        rect(LI, 0.565, 1.495, 2.17, 1.665)                     # high bar
        rect(LI, 0.565, 1.495, 0.895, 2.465)                    # Y p-fingers
        rect(LI, 1.405, 1.495, 1.735, 2.465)
        pin(cell, rect, "A", 0.27)
        pin(cell, rect, "Y", 2.07)
    frame(cell, rect, W)
    lib.add(cell)
    return W


def nand2(lib, name):
    """Series nfets (outer contacts, internal node uncontacted), parallel
    pfets (common middle drain). B hooks LEFT, A hooks RIGHT; Y necks
    between the two pad patches with 0.17 each side."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 3 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.155, *_y(NDIFF_Y, 1.245))
    rect(DIFF, 0.155, *_y(PDIFF_Y, 1.245))
    rect(POLY, 0.415, POLY_Y[0], 0.565, POLY_Y[1])              # gate B
    rect(POLY, 0.105, HOOK_Y[0], 0.415, HOOK_Y[1])
    rect(POLY, 0.835, POLY_Y[0], 0.985, POLY_Y[1])              # gate A
    rect(POLY, 0.985, HOOK_Y[0], 1.275, HOOK_Y[1])
    rect(LICON, 0.18, PADCUT_Y[0], 0.35, PADCUT_Y[1])           # B licon
    rect(LICON, 1.02, PADCUT_Y[0], 1.19, PADCUT_Y[1])           # A licon
    # n rows drop to (0.635,0.805): the VGND stub tops at 0.885 and the
    # licon needs its 0.08 li enclosure from it (li.5)
    nrows = [(0.295, 0.465), (0.635, 0.805)]
    licons(rect, 0.28, nrows + PROWS)       # n chain end (VGND) + p source
    licons(rect, 0.70, PROWS)               # p common drain (Y)
    licons(rect, 1.12, nrows + PROWS)       # n chain end (Y) + p source
    rect(LI, 0.095, 1.055, 0.43, 1.325)                         # B patch
    rect(LI, 0.94, 1.075, 1.275, 1.325)                         # A patch
    rect(LI, 0.085, 0.085, 0.395, 0.885)                        # VGND stub
    rect(LI, 0.085, 1.495, 0.365, 2.635)                        # VPWR stubs
    rect(LI, 1.035, 1.495, 1.295, 2.635)
    rect(LI, 0.6, 0.255, 1.295, 0.885)                          # Y n-slab
    rect(LI, 0.6, 0.885, 0.77, 1.485)                           # Y neck
    rect(LI, 0.535, 1.485, 0.865, 2.465)                        # Y p-slab
    pin(cell, rect, "B", 0.225)
    pin(cell, rect, "A", 1.145)
    pin(cell, rect, "Y", 0.685)
    lib.add(cell)
    return W


def nor2(lib, name):
    """Mirror of NAND2: series pfets (left contact = Y drain, right =
    VPWR, middle uncontacted), parallel nfets (middle common drain). The
    A gate doglegs 0.06 left between the diffs so its pdiff finger clears
    the pad hook; Y climbs the left pdiff column."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 3 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.135, *_y(NDIFF_Y, 1.225))
    rect(DIFF, 0.135, *_y(PDIFF_Y, 1.165))
    rect(POLY, 0.395, POLY_Y[0], 0.545, POLY_Y[1])              # gate B
    rect(POLY, 0.11, HOOK_Y[0], 0.395, HOOK_Y[1])
    rect(POLY, 0.815, POLY_Y[0], 0.965, 1.175)                  # gate A (n)
    rect(POLY, 0.755, 1.175, 0.905, POLY_Y[1])                  # gate A (p)
    rect(POLY, 0.755, HOOK_Y[0], 0.965, HOOK_Y[1])              # dogleg
    rect(POLY, 0.965, HOOK_Y[0], 1.275, HOOK_Y[1])              # A hook
    rect(LICON, 0.185, PADCUT_Y[0], 0.355, PADCUT_Y[1])         # B licon
    rect(LICON, 1.025, PADCUT_Y[0], 1.195, PADCUT_Y[1])         # A licon
    nrows = [(0.305, 0.475), (0.645, 0.815)]
    licons(rect, 0.26, nrows)               # n source (VGND)
    licons(rect, 0.68, nrows)               # n common drain (Y)
    licons(rect, 1.10, nrows)               # n source (VGND)
    licons(rect, 0.26, PROWS)               # p chain end (Y)
    licons(rect, 1.04, PROWS)               # p chain end (VPWR)
    rect(LI, 0.085, 1.075, 0.435, 1.325)                        # B patch
    rect(LI, 0.945, 1.075, 1.295, 1.325)                        # A patch
    rect(LI, 0.105, 0.085, 0.345, 0.895)                        # VGND stubs
    rect(LI, 1.015, 0.085, 1.285, 0.895)
    rect(LI, 0.955, 1.495, 1.285, 2.635)                        # VPWR stub
    rect(LI, 0.515, 0.255, 0.845, 0.895)                        # Y n-slab
    rect(LI, 0.605, 0.895, 0.775, 1.495)                        # Y neck
    rect(LI, 0.095, 1.495, 0.775, 1.665)                        # Y run left
    rect(LI, 0.095, 1.495, 0.425, 2.45)                         # Y p-riser
    pin(cell, rect, "B", 0.23)
    pin(cell, rect, "A", 1.15)
    pin(cell, rect, "Y", 0.235, 2.21)
    lib.add(cell)
    return W


def buf_x1(lib, name):
    """BUF_X1: minimum buffer — one finger per stage, 4 sites. Purpose:
    the HOLD-FIX cell. OpenROAD's repair_hold picks the buffer with the
    highest hold-delay/area metric; BUF_X1 (~2x INV_X1's delay in
    BUF_X2's area) beats BUF_X2 ~2.3x on it, roughly halving the
    hold-buffer area that killed the all-own-cells 1x1 floorplan.
    Topology = buf_x2's stage-1 recipe with a single stage-2 finger;
    the Y bar carries an extended mid-band neck so the pin marker fits
    with 0.17 to the yb pad patch."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 4 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.135, *_y(NDIFF_Y, 1.285))
    rect(DIFF, 0.135, *_y(PDIFF_Y, 1.285))
    rect(POLY, 0.395, POLY_Y[0], 0.545, POLY_Y[1])              # gate A
    rect(POLY, 0.135, HOOK_Y[0], 0.395, HOOK_Y[1])
    rect(POLY, 0.87, POLY_Y[0], 1.02, POLY_Y[1])                # gate yb
    rect(POLY, 0.755, HOOK_Y[0], 0.87, HOOK_Y[1])
    rect(LICON, 0.185, PADCUT_Y[0], 0.355, PADCUT_Y[1])         # A licon
    rect(LICON, 0.805, PADCUT_Y[0], 0.975, PADCUT_Y[1])         # yb licon
    licons(rect, 0.26, [(0.36, 0.53), (1.875, 2.045), (2.215, 2.385)])
    licons(rect, 0.725, [NROWS[0], (1.875, 2.045), (2.215, 2.385)])
    licons(rect, 1.155, [(0.445, 0.615), (1.73, 1.9), (2.135, 2.305)])
    rect(LI, 0.085, 0.985, 0.44, 1.355)                         # A patch
    rect(LI, 0.56, 0.085, 0.89, 0.465)                          # VGND stub
    rect(LI, 0.56, 1.875, 0.89, 2.635)                          # VPWR stub
    rect(LI, 0.175, 0.255, 0.345, 0.805)                        # yb n-finger
    rect(LI, 0.175, 0.635, 0.78, 0.805)                         # yb low arm
    rect(LI, 0.61, 0.805, 0.78, 1.535)                          # yb riser
    rect(LI, 0.725, 0.995, 0.975, 1.325)                        # yb pad li
    rect(LI, 0.175, 1.535, 0.78, 1.705)                         # yb high arm
    rect(LI, 0.175, 1.535, 0.345, 2.465)                        # yb p-finger
    rect(LI, 1.07, 0.255, 1.24, 0.825)                          # Y lower
    rect(LI, 1.07, 0.655, 1.315, 0.825)      # widened throat (li.1: the
    rect(LI, 1.145, 0.825, 1.315, 1.495)     # Y neck's x-overlap with the
    rect(LI, 1.07, 1.495, 1.315, 1.665)      # bars must be >= 0.17)
    rect(LI, 1.07, 1.495, 1.24, 2.465)                          # Y upper
    pin(cell, rect, "A", 0.23)
    pin(cell, rect, "Y", 1.23)
    lib.add(cell)
    return W


def buf_x2(lib, name):
    """Stage 1 (gate A, pad hook left) drives yb: drain fingers at the
    LEFT EDGE column, arms reaching right between the rails' stub rows to
    the stage-2 strap pad. Stage 2 = inv pair; its drain licons shift off
    the standard rows wherever a yb arm needs its 0.17."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 4 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.135, *_y(NDIFF_Y, 1.705))
    rect(DIFF, 0.135, *_y(PDIFF_Y, 1.705))
    rect(POLY, 0.395, POLY_Y[0], 0.545, POLY_Y[1])              # gate A
    rect(POLY, 0.135, HOOK_Y[0], 0.395, HOOK_Y[1])
    for gx in (0.945, 1.365):                                   # stage 2
        rect(POLY, gx - 0.075, POLY_Y[0], gx + 0.075, POLY_Y[1])
    rect(POLY, 0.755, HOOK_Y[0], 1.44, HOOK_Y[1])               # strap+pad
    rect(LICON, 0.185, PADCUT_Y[0], 0.355, PADCUT_Y[1])         # A licon
    rect(LICON, 0.805, PADCUT_Y[0], 0.975, PADCUT_Y[1])         # yb licon
    licons(rect, 0.26, [(0.36, 0.53), (1.875, 2.045), (2.215, 2.385)])
    licons(rect, 0.725, [NROWS[0], (1.875, 2.045), (2.215, 2.385)])
    # drain licons center at 1.155 — midway between the gate EDGES
    # (1.02..1.29), not the 1.15 column center: at 1.15 the gate gap is
    # 0.045 < 0.05 (licon.11) — found by magic, missed by the klayout
    # deck's rule formulation
    licons(rect, 1.155, [(0.445, 0.615), (1.73, 1.9), (2.135, 2.305)])
    licons(rect, 1.575, [(0.315, 0.485), NROWS[1]] + PROWS)
    rect(LI, 0.085, 0.985, 0.44, 1.355)                         # A patch
    rect(LI, 0.56, 0.085, 0.89, 0.465)                          # VGND stubs
    rect(LI, 1.49, 0.085, 1.75, 0.925)
    rect(LI, 0.56, 1.875, 0.89, 2.635)                          # VPWR stubs
    rect(LI, 1.49, 1.485, 1.75, 2.635)
    rect(LI, 0.175, 0.255, 0.345, 0.805)                        # yb n-finger
    rect(LI, 0.175, 0.635, 0.89, 0.805)                         # yb low arm
    rect(LI, 0.72, 0.805, 0.89, 1.535)                          # yb riser
    rect(LI, 0.89, 0.995, 0.975, 1.325)                         # yb pad li
    rect(LI, 0.175, 1.535, 0.89, 1.705)                         # yb high arm
    rect(LI, 0.175, 1.535, 0.345, 2.465)                        # yb p-finger
    rect(LI, 1.06, 0.255, 1.315, 0.83)                          # Y lower
    rect(LI, 1.145, 0.83, 1.315, 1.56)                          # Y neck
    rect(LI, 1.06, 1.56, 1.315, 2.465)                          # Y upper
    pin(cell, rect, "A", 0.23)
    pin(cell, rect, "Y", 1.23)
    lib.add(cell)
    return W


def buf_x4(lib, name):
    """buf_x2 scaled: stage 2 = 4 fingers (2 drain columns joined by bars
    + a mid-band slab carrying the pin)."""
    cell = gdstk.Cell(name)
    rect = _mk(cell)
    W = 6 * SITE
    frame(cell, rect, W)
    rect(DIFF, 0.135, *_y(NDIFF_Y, 2.485))
    rect(DIFF, 0.135, *_y(PDIFF_Y, 2.485))
    rect(POLY, 0.395, POLY_Y[0], 0.545, POLY_Y[1])              # gate A
    rect(POLY, 0.14, 1.015, 0.395, 1.305)
    for gx in (0.89, 1.31, 1.73, 2.15):                         # stage 2
        rect(POLY, gx - 0.075, POLY_Y[0], gx + 0.075, POLY_Y[1])
    rect(POLY, 0.81, 1.025, 2.225, 1.295)                       # strap
    rect(LICON, 0.22, PADCUT_Y[0], 0.39, PADCUT_Y[1])           # A licon
    rect(LICON, 0.89, PADCUT_Y[0], 1.06, PADCUT_Y[1])           # yb licon
    licons(rect, 0.26, [(0.475, 0.645), (1.545, 1.715),
                        (1.885, 2.055), (2.225, 2.395)])        # s1 drain
    licons(rect, 0.68, [(0.315, 0.485), PROWS[1], PROWS[2]])    # s1 source
    licons(rect, 1.10, [(0.475, 0.645), (1.67, 1.84), (2.145, 2.315)])
    licons(rect, 1.52, [(0.315, 0.485), PROWS[1], PROWS[2]])    # s2 source
    licons(rect, 1.94, [(0.475, 0.645), (1.67, 1.84), (2.145, 2.315)])
    licons(rect, 2.36, [(0.295, 0.465), (0.635, 0.805)] + PROWS)
    rect(LI, 0.09, 1.075, 0.47, 1.315)                          # A patch
    rect(LI, 0.525, 0.085, 0.765, 0.565)                        # VGND stubs
    rect(LI, 1.355, 0.085, 1.685, 0.565)
    rect(LI, 2.195, 0.085, 2.525, 0.885)
    rect(LI, 0.595, 1.835, 0.835, 2.635)                        # VPWR stubs
    rect(LI, 1.355, 1.835, 1.685, 2.635)
    rect(LI, 2.195, 1.485, 2.525, 2.635)
    rect(LI, 0.175, 0.255, 0.345, 0.905)                        # yb n-finger
    rect(LI, 0.175, 0.735, 0.81, 0.905)                         # yb low arm
    rect(LI, 0.64, 0.905, 0.81, 1.485)                          # yb riser
    rect(LI, 0.81, 1.075, 1.14, 1.245)                          # yb pad li
    rect(LI, 0.095, 1.485, 0.81, 1.655)                         # yb high arm
    rect(LI, 0.095, 1.655, 0.425, 2.465)                        # yb p-finger
    rect(LI, 1.015, 0.255, 1.185, 0.905)                        # Y n-fingers
    rect(LI, 1.855, 0.255, 2.025, 0.905)
    rect(LI, 1.015, 0.735, 2.025, 0.905)                        # low bar
    rect(LI, 1.53, 0.905, 2.025, 1.445)                         # pin slab
    rect(LI, 1.015, 1.445, 2.025, 1.615)                        # high bar
    rect(LI, 1.015, 1.615, 1.185, 2.465)                        # Y p-fingers
    rect(LI, 1.855, 1.615, 2.025, 2.465)
    pin(cell, rect, "A", 0.305)
    pin(cell, rect, "Y", 1.615)
    lib.add(cell)
    return W


GENERATORS = {
    "INV_X1": inv_x1,
    "INV_X2": lambda l, n: inv_multi(l, n, 2),
    "INV_X4": lambda l, n: inv_multi(l, n, 4),
    "NAND2_X1": nand2,
    "NOR2_X1": nor2,
    "BUF_X1": buf_x1,
    "BUF_X2": buf_x2,
    "BUF_X4": buf_x4,
}

if __name__ == "__main__":
    import json
    outdir = Path(__file__).parents[1] / "out"
    areas = {}
    for name, fn in GENERATORS.items():
        lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)
        w = fn(lib, name)
        lib.write_gds(str(outdir / f"{name.lower()}.gds"))
        areas[name] = round(w * H, 4)
        print(f"{name}: W = {w:.2f} um ({w/SITE:.0f} sites), "
              f"area {areas[name]} um2 -> {name.lower()}.gds")
    (outdir / "areas_real.json").write_text(json.dumps(areas, indent=1))
