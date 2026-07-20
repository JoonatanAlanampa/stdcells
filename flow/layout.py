"""Phase 5: cell layouts, starting with INV_X1.

Geometry: sky130 hd frame — 2.72 um row, 0.46 um sites, met1 rails top and
bottom. Both devices folded into TWO fingers (S-G-D-G-S) so the measured
Wp = 1.7 um fits the row: pdiff 2 x 0.85, ndiff 2 x 0.325.

Cell width: 4 sites. The first DRC round proved 3 sites impossible: with
folding, the middle column must carry the output li strap, so the input
poly contact needs its own column (the foundry's own 2-finger inv_2 is
4 sites for the same reason). All rule values are named constants, tuned
against the PDK KLayout DRC deck.
"""
import gdstk

# GDS layer map (sky130A)
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

# frame
H = 2.72
SITE = 0.46
W = 4 * SITE            # 1.84 um — see docstring
RAIL_W = 0.48

# device geometry
WP_F = 0.85             # pmos finger width (x2 = 1.70)
WN_F = 0.325            # nmos finger width (x2 = 0.65)
LGATE = 0.15
XC = [0.23, 0.69, 1.15]         # S, D, S contact columns
XG = [0.46, 0.92]               # gate fingers

# rules (tuned against sky130A_mr.drc)
CUT = 0.17
DIFF_ENC_LICON = 0.06
POLY_ENDCAP = 0.13
NPC_ENC = 0.10
SDM_ENC = 0.125
NWELL_ENC = 0.18
LI_W = 0.17
LI_ENC_LICON = 0.08
GRID = 0.005

PDIFF_Y = (1.41, 1.41 + WP_F)          # 1.41 .. 2.26
NDIFF_Y = (0.36, 0.36 + WN_F)          # 0.36 .. 0.685
PY_CUT = 1.835                          # pdiff licon row (on grid)
NY_CUT = 0.52                           # ndiff licon row (on grid)
PAD = (1.52, 1.13)                      # input poly-contact licon center
POLY_PAD = 0.33

lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)
cell = gdstk.Cell("INV_X1")


def rect(layer, x0, y0, x1, y1):
    cell.add(gdstk.rectangle((round(x0, 3), round(y0, 3)),
                             (round(x1, 3), round(y1, 3)),
                             layer=layer[0], datatype=layer[1]))


# boundary + rails
rect(BND, 0, 0, W, H)
rect(MET1, 0, -RAIL_W / 2, W, RAIL_W / 2)
rect(MET1, 0, H - RAIL_W / 2, W, H + RAIL_W / 2)

# diffusions
dx0 = XC[0] - CUT / 2 - DIFF_ENC_LICON
dx1 = XC[2] + CUT / 2 + DIFF_ENC_LICON
pd0, pd1 = PDIFF_Y
nd0, nd1 = NDIFF_Y
rect(DIFF, dx0, pd0, dx1, pd1)
rect(DIFF, dx0, nd0, dx1, nd1)
rect(PSDM, dx0 - SDM_ENC, pd0 - SDM_ENC, dx1 + SDM_ENC, pd1 + SDM_ENC)
rect(NSDM, dx0 - SDM_ENC, nd0 - SDM_ENC, dx1 + SDM_ENC, nd1 + SDM_ENC)
rect(NWELL, dx0 - NWELL_ENC, pd0 - NWELL_ENC, dx1 + NWELL_ENC, H + 0.19)

# poly: two fingers + horizontal strap to the input pad column
for xg in XG:
    rect(POLY, xg - LGATE / 2, nd0 - POLY_ENDCAP,
         xg + LGATE / 2, pd1 + POLY_ENDCAP)
rect(POLY, XG[0] - LGATE / 2, PAD[1] - 0.075,
     PAD[0] + POLY_PAD / 2, PAD[1] + 0.075)
rect(POLY, PAD[0] - POLY_PAD / 2, PAD[1] - POLY_PAD / 2,
     PAD[0] + POLY_PAD / 2, PAD[1] + POLY_PAD / 2)
rect(NPC, PAD[0] - CUT / 2 - NPC_ENC, PAD[1] - CUT / 2 - NPC_ENC,
     PAD[0] + CUT / 2 + NPC_ENC, PAD[1] + CUT / 2 + NPC_ENC)
rect(LICON, PAD[0] - CUT / 2, PAD[1] - CUT / 2,
     PAD[0] + CUT / 2, PAD[1] + CUT / 2)

# diff licons
for xc in XC:
    rect(LICON, xc - CUT / 2, PY_CUT - CUT / 2, xc + CUT / 2, PY_CUT + CUT / 2)
    rect(LICON, xc - CUT / 2, NY_CUT - CUT / 2, xc + CUT / 2, NY_CUT + CUT / 2)

# li wiring: sources to rails, drains joined as Y, pad as A
for xc in (XC[0], XC[2]):
    rect(LI, xc - LI_W / 2, PY_CUT - CUT / 2 - LI_ENC_LICON, xc + LI_W / 2, H)
    rect(LI, xc - LI_W / 2, 0, xc + LI_W / 2, NY_CUT + CUT / 2 + LI_ENC_LICON)
rect(LI, XC[1] - LI_W / 2, NY_CUT - CUT / 2 - LI_ENC_LICON,
     XC[1] + LI_W / 2, PY_CUT + CUT / 2 + LI_ENC_LICON)
rect(LI, PAD[0] - CUT / 2 - LI_ENC_LICON, PAD[1] - LI_W / 2,
     PAD[0] + CUT / 2 + LI_ENC_LICON, PAD[1] + LI_W / 2)

# mcons under the rails on the source columns
for xc in (XC[0], XC[2]):
    rect(MCON, xc - CUT / 2, H - CUT, xc + CUT / 2, H)
    rect(MCON, xc - CUT / 2, 0, xc + CUT / 2, CUT)

# pins
rect(LIPIN, XC[1] - LI_W / 2, 1.13 - 0.085, XC[1] + LI_W / 2, 1.13 + 0.085)
cell.add(gdstk.Label("Y", (XC[1], 1.13), layer=LILBL[0], texttype=LILBL[1]))
rect(LIPIN, PAD[0] - 0.085, PAD[1] - 0.085, PAD[0] + 0.085, PAD[1] + 0.085)
cell.add(gdstk.Label("A", PAD, layer=LILBL[0], texttype=LILBL[1]))
cell.add(gdstk.Label("VPWR", (W / 2, H), layer=MET1LBL[0],
                     texttype=MET1LBL[1]))
cell.add(gdstk.Label("VGND", (W / 2, 0), layer=MET1LBL[0],
                     texttype=MET1LBL[1]))

lib.add(cell)
from pathlib import Path
out = Path(__file__).parents[1] / "out" / "inv_x1.gds"
lib.write_gds(str(out))
print(f"wrote {out}")
