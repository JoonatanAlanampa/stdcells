"""Off-bin RECTANGULAR nfet_01v8 test devices for the v3 gate-check.

The v3 plan (V3-PLAN.md) pinned a W ~ 0.25 um NMOS as the "devphys where BSIM
stops" proof device: model_bins.py flags it OFF-BIN (no BSIM bin exists in
W in [0.15, 0.36)) yet it is DRC-legal on the *KLayout* manufacturing deck
(difftap.1 floor = 0.15 um). This draws that device -- plus an in-bin control
at the diff/tap.2 std floor W = 0.42 um -- so magic (in CI) can adjudicate the
real question the KLayout deck cannot see:

    is a rectangular gated transistor at W < 0.42 um sign-off-legal, or is it
    forbidden by magic diff/tap.2 "Transistor width < 0.42 um" -- the same class
    of dead-end that poly.11 was for the annular device?

magic sky130A.tech line 4771:
    edge4way *poly allfetsstd 420 allfets 0 0   "Transistor width < %d (diff/tap.2)"
    edge4way *poly allfetsspecial 360 allfets 0 0   "... in standard cell < 0.36"
The KLayout sky130A_mr.drc has NO transistor-width rule (only difftap.1 = 0.15
on the plain-diff shape). So this is the sharpest possible KLayout-clean !=
rule-clean test.

Layout per device (DOGBONE, origin at channel centre; current flows in X):
  - DIFF narrow strip (height = W) under the gate  -> sets the transistor width
    that diff/tap.2 measures; flares to 0.42-tall S/D contact PADS away from the
    gate so the licons are cleanly enclosed even at W = 0.25.
  - POLY gate crosses the strip (L = 0.15 in X), endcaps over field (poly.8),
    and rises to a contact PAD over field with an NPC cut for the gate licon.
  - nsdm over all diff (+ enclosure)  => nfet.
  - licon/li/mcon/met1 + labels on S, D, G for extraction + LVS.

sky130 GDS layers from stdcells/flow/layout.py.
"""
import sys
import gdstk

# (layer, datatype)
DIFF = (65, 20); NSDM = (93, 44); POLY = (66, 20); NPC = (95, 20)
LICON = (66, 44); LI = (67, 20); MCON = (67, 44)
MET1 = (68, 20); MET1LBL = (68, 5)

L = 0.15           # channel length = poly width in X
LIC = 0.17         # licon / mcon size
SD = 0.30          # S/D diff extension in X beyond the gate edge (>= poly.7)
STRIP_HX = 0.20    # narrow-strip half-extent in X (gate +-0.075 sits inside)
WPAD = 0.42        # S/D contact-pad diff height (licon fits with margin)
ENC_D = 0.06       # diff/li enclosure of licon (>= licon.5a 0.04)
NSDM_ENC = 0.125   # nsdm enclosure of diff


def rect(cell, lay, x0, y0, x1, y1):
    cell.add(gdstk.rectangle((round(x0, 4), round(y0, 4)),
                             (round(x1, 4), round(y1, 4)),
                             layer=lay[0], datatype=lay[1]))


def contact(cell, name, cx, cy, on_poly=False):
    """licon + li + mcon + met1 pad + met1 label at (cx, cy)."""
    rect(cell, LICON, cx - LIC/2, cy - LIC/2, cx + LIC/2, cy + LIC/2)
    rect(cell, LI, cx - LIC/2 - 0.08, cy - LIC/2 - 0.08,
         cx + LIC/2 + 0.08, cy + LIC/2 + 0.08)
    rect(cell, MCON, cx - LIC/2, cy - LIC/2, cx + LIC/2, cy + LIC/2)
    rect(cell, MET1, cx - LIC/2 - 0.07, cy - LIC/2 - 0.07,
         cx + LIC/2 + 0.07, cy + LIC/2 + 0.07)
    cell.add(gdstk.Label(name, (cx, cy), layer=MET1LBL[0], texttype=MET1LBL[1]))


def build(W):
    """Return a gdstk.Library holding one dogbone nfet of channel width W."""
    name = f"nfet_w{int(round(W*1000)):03d}"
    lib = gdstk.Library(name, unit=1e-6, precision=1e-9)
    c = lib.new_cell(name)

    gx = L / 2                      # gate half-width in X = 0.075
    pad_x0 = STRIP_HX               # S/D pad inner X edge
    pad_x1 = STRIP_HX + SD          # S/D pad outer X edge

    # --- DIFF dogbone: narrow strip (height W) + two wide S/D pads ---
    diff_parts = [
        gdstk.rectangle((-STRIP_HX, -W/2), (STRIP_HX, W/2)),          # strip
        gdstk.rectangle((-pad_x1, -WPAD/2), (-pad_x0, WPAD/2)),       # src pad
        gdstk.rectangle((pad_x0, -WPAD/2), (pad_x1, WPAD/2)),         # drn pad
    ]
    diff = gdstk.boolean(diff_parts, [], "or", layer=DIFF[0], datatype=DIFF[1])
    c.add(*diff)

    # --- nsdm over all diff (+ enclosure) => nfet ---
    rect(c, NSDM, -pad_x1 - NSDM_ENC, -WPAD/2 - NSDM_ENC,
         pad_x1 + NSDM_ENC, WPAD/2 + NSDM_ENC)

    # --- POLY gate: crosses the strip, endcaps over field, rises to a pad ---
    endcap = W/2 + 0.13                        # poly.8 endcap >= 0.13
    # gate contact pad sits at a W-INDEPENDENT height so its li clears the S/D
    # li by >= 0.17 (li.3) even at the narrowest W; the channel width under the
    # gate -- the only thing diff/tap.2 measures -- is unaffected by this.
    gate_pad_y0 = max(endcap + 0.05, 0.40)
    gate_pad_y1 = gate_pad_y0 + 0.30
    poly_parts = [
        gdstk.rectangle((-gx, -endcap), (gx, gate_pad_y0)),          # gate + arm
        gdstk.rectangle((-0.16, gate_pad_y0), (0.16, gate_pad_y1)),  # contact pad
    ]
    poly = gdstk.boolean(poly_parts, [], "or", layer=POLY[0], datatype=POLY[1])
    c.add(*poly)

    # NPC (nitride poly cut) over the gate contact pad, enclosing the licon
    gcy = (gate_pad_y0 + gate_pad_y1) / 2
    rect(c, NPC, -0.21, gate_pad_y0 - 0.05, 0.21, gate_pad_y1 + 0.05)

    # --- contacts: source, drain, gate ---
    contact(c, "S", -(pad_x0 + pad_x1) / 2, 0.0)
    contact(c, "D", (pad_x0 + pad_x1) / 2, 0.0)
    contact(c, "G", 0.0, gcy, on_poly=True)

    fname = f"{name}.gds"
    lib.write_gds(fname)

    # netgen LVS reference: the device magic SHOULD extract -- one nfet_01v8
    # at the drawn W/L, terminals D/G/S + substrate. LVS proves the tools bind
    # it fine (device identity + params); the DRC verdict is separate.
    with open(f"{name}_ref.spice", "w") as fp:
        fp.write(f"* reference: single nfet_01v8, W={W}um L={L}um\n"
                 f".subckt {name} D G S VSUBS\n"
                 f"X0 D G S VSUBS sky130_fd_pr__nfet_01v8 "
                 f"w={W:g}u l={L:g}u\n"
                 f".ends\n")

    (x0, y0), (x1, y1) = c.bounding_box()
    print(f"wrote {fname} + {name}_ref.spice  W={W} um L={L} um  "
          f"bbox {x1-x0:.3f} x {y1-y0:.3f} um "
          f"(transistor width under gate = {W} um)")
    return name


if __name__ == "__main__":
    # W=0.25 : OFF-BIN target (below the 0.36 BSIM floor AND the 0.42 magic floor)
    # W=0.42 : diff/tap.2 std floor, IN-BIN control (expected magic-clean)
    widths = [float(a) for a in sys.argv[1:]] or [0.25, 0.42]
    for w in widths:
        build(w)
