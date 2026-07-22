"""Annular (enclosed-gate) nfet_01v8 for the v3 scope-b GATE-CHECK.

The research (custom-devices.md, Q2) says ring-gate devices have no primary
source and probably mis-extract / have no defined W. This draws ONE minimal
annular nfet so magic (in CI) can answer: does it extract as an nfet at all,
and with what W/L? DRC-cleanliness is secondary here -- extraction is the
question -- but we run KLayout DRC locally as a first signal.

Layout (concentric, origin at centre):
  - DRAIN  = a difftap island in the middle, one licon.
  - GATE   = a POLY ring (frame of thickness L) sitting on the difftap; the
             channel is the difftap under the ring. A poly arm exits to the
             RIGHT over a NOTCH cut in the difftap (so the gate contact lands
             over field, not over source diff -- the classic annular trick).
  - SOURCE = the difftap OUTSIDE the ring (top/bottom/left), licon'd.
  - nsdm over all difftap => nfet. li/mcon/met1 + labels per terminal.

sky130 GDS layers from stdcells/flow/layout.py.
"""
import gdstk

# (layer, datatype)
DIFF = (65, 20); NSDM = (93, 44); POLY = (66, 20)
LICON = (66, 44); LI = (67, 20); MCON = (67, 44)
MET1 = (68, 20); MET1LBL = (68, 5)

L = 0.15          # channel length = poly ring thickness
LIC = 0.17        # licon/mcon size
ENC = 0.06        # diff/li enclosure of licon (>= licon.5a 0.04)
G2C = 0.055       # licon-to-gate (licon.11)

R_in = 0.16       # poly ring inner half-extent (drain side)
R_out = R_in + L  # = 0.31, poly ring outer half-extent
S_lic = 0.55      # source licon centre offset
DTAP = 0.70       # difftap half-extent (square side 1.20 um)


def sq(hw, cx=0.0, cy=0.0):
    return gdstk.rectangle((cx - hw, cy - hw), (cx + hw, cy + hw))


def box(x0, y0, x1, y1):
    return gdstk.rectangle((x0, y0), (x1, y1))


def lic_stack(cell, cx, cy):
    """licon + li + mcon + met1 pad at (cx,cy)."""
    for lay, hw in ((LICON, LIC / 2), (LI, LIC / 2 + 0.08),
                    (MCON, LIC / 2), (MET1, LIC / 2 + 0.07)):
        cell.add(sq(hw, cx, cy).copy()) if False else \
            cell.add(gdstk.rectangle((cx - hw, cy - hw), (cx + hw, cy + hw),
                                     layer=lay[0], datatype=lay[1]))


def main():
    lib = gdstk.Library()
    c = lib.new_cell("annular_nfet")

    # --- difftap: full square MINUS a notch on the right for the gate exit ---
    notch = box(R_out, -0.14, DTAP + 0.30, 0.14)     # cut the source diff open
    diff = gdstk.boolean(sq(DTAP), notch, "not", layer=DIFF[0], datatype=DIFF[1])
    c.add(*diff)

    # --- nsdm over all diff (+enclosure) => nfet ---
    c.add(gdstk.rectangle((-DTAP - 0.13, -DTAP - 0.13), (DTAP + 0.13, DTAP + 0.13),
                          layer=NSDM[0], datatype=NSDM[1]))

    # --- poly ring (frame) + arm to a gate pad over the notch/field ---
    ring = gdstk.boolean(sq(R_out), sq(R_in), "not")
    arm = box(R_in, -0.075, 0.80, 0.075)            # exits right over the notch
    pad = box(0.63, -0.11, 0.82, 0.11)              # gate contact pad
    poly = gdstk.boolean(gdstk.boolean(ring, arm, "or"), pad, "or",
                         layer=POLY[0], datatype=POLY[1])
    c.add(*poly)

    # --- contacts: drain (centre), source (3 sides), gate (pad) ---
    lic_stack(c, 0.0, 0.0)                           # DRAIN
    for (cx, cy) in ((0.0, S_lic), (0.0, -S_lic), (-S_lic, 0.0)):
        lic_stack(c, cx, cy)                         # SOURCE ring
    lic_stack(c, 0.72, 0.0)                          # GATE (on poly pad)

    # --- terminal labels (met1) for LVS port id ---
    for name, (x, y) in (("D", (0, 0)), ("S", (0, S_lic)), ("G", (0.72, 0))):
        c.add(gdstk.Label(name, (x, y), layer=MET1LBL[0], texttype=MET1LBL[1]))

    lib.write_gds("annular_nfet.gds")
    # bbox for the record
    (x0, y0), (x1, y1) = c.bounding_box()
    print(f"wrote annular_nfet.gds  bbox {x1-x0:.3f} x {y1-y0:.3f} um")
    print(f"design intent: annular nfet, L={L}um, poly ring {2*R_in:.2f}->"
          f"{2*R_out:.2f}um, enclosed drain + ring source + field gate exit")


if __name__ == "__main__":
    main()
