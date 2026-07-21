"""Phase 6 prep: LEF abstracts for the 7 verified cells.

Reads the DRC/LVS-verified GDS back (so the abstract derives from the
exact polygons that passed signoff): pin ports are the full connected
li/met1 polygon under each label (maximum router access), rails are
POWER/GROUND abutment pins, everything else on li1/met1 becomes OBS.
Site: unithd (0.46 x 2.72). Emits out/own.lef + a merged out/own_cells.gds.
"""
from pathlib import Path

import gdstk

OUT = Path(__file__).parents[1] / "out"
LI = (67, 20)
LIPIN = (67, 16)
LILBL = (67, 5)
MET1 = (68, 20)
MET1LBL = (68, 5)
BND = (235, 4)

CELLS = ["INV_X1", "INV_X2", "INV_X4", "BUF_X1", "BUF_X2", "BUF_X4",
         "NAND2_X1", "NOR2_X1", "DFF_X1", "TIE_X1", "WELLTAP_X1",
         "DIODE_X1", "FILL_X1", "FILL_X2", "FILL_X4", "FILL_X8"]
LEF_CLASS = {"WELLTAP_X1": "CORE WELLTAP", "DIODE_X1": "CORE ANTENNACELL",
             "FILL_X1": "CORE SPACER", "FILL_X2": "CORE SPACER",
             "FILL_X4": "CORE SPACER", "FILL_X8": "CORE SPACER"}
OUTPUT_PINS = ("Y", "Q", "HI", "LO")


def polys_on(cell, layer):
    return [p for p in cell.polygons
            if (p.layer, p.datatype) == layer]


def merged(polys):
    return gdstk.boolean(polys, [], "or") if polys else []


def find_containing(polys, pt):
    for p in polys:
        if gdstk.inside([pt], [p])[0]:
            return p
    return None


def bbox(p):
    (x0, y0), (x1, y1) = p.bounding_box()
    return x0, y0, x1, y1


def rects(p):
    """Exact rectangle decomposition of a rectilinear polygon: horizontal
    slabs cut at every distinct y. v2 pin/obs polygons snake through the
    mid-band — their bounding box would cover half the cell, telling the
    router metal (or blockage) exists where it does not."""
    ys = sorted({round(y, 4) for _, y in p.points})
    out = []
    for y0, y1 in zip(ys, ys[1:]):
        strip = gdstk.rectangle((bbox(p)[0] - 1, y0), (bbox(p)[2] + 1, y1))
        for piece in gdstk.boolean([p], [strip], "and"):
            out.append(bbox(piece))
    # merge vertically-adjacent slabs with identical x extents
    out.sort()
    merged = []
    for r in out:
        if merged and abs(merged[-1][0] - r[0]) < 1e-6 and \
                abs(merged[-1][2] - r[2]) < 1e-6 and \
                abs(merged[-1][3] - r[1]) < 1e-6:
            merged[-1] = (r[0], merged[-1][1], r[2], r[3])
        else:
            merged.append(tuple(r))
    return merged


lef = ["VERSION 5.7 ;", "BUSBITCHARS \"[]\" ;", "DIVIDERCHAR \"/\" ;", ""]
merged_lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)

for name in CELLS:
    gds = gdstk.read_gds(str(OUT / f"{name.lower()}.gds"))
    cell = [c for c in gds.cells if c.name == name][0]
    merged_lib.add(cell.copy(name))

    (bx0, by0), (bx1, by1) = \
        polys_on(cell, BND)[0].bounding_box()
    W, H = bx1 - bx0, by1 - by0

    li_polys = merged(polys_on(cell, LI))
    m1_polys = merged(polys_on(cell, MET1))

    # signal pins: label -> connected polygon on its layer
    pins = {}
    for lbl in cell.labels:
        key = (lbl.layer, lbl.texttype)
        if key == LILBL and lbl.text not in ("VPWR", "VGND"):
            poly = find_containing(li_polys, lbl.origin)
            pins[lbl.text] = ("li1", poly)
        elif key == MET1LBL and lbl.text not in ("VPWR", "VGND"):
            poly = find_containing(m1_polys, lbl.origin)
            pins[lbl.text] = ("met1", poly)

    # rails
    rails = {}
    for lbl in cell.labels:
        if lbl.text in ("VPWR", "VGND"):
            rails[lbl.text] = find_containing(m1_polys, lbl.origin)

    # TIE_X1: restrict the pin ports to the pad-patch band. The full
    # connected HI/LO polygons let the router drop via pairs on adjacent
    # tracks of the wide bands (li squares 0.16 apart) and vias hemmed
    # in by neighbor-cell li - all 64 li.3 violations of the first
    # zero-foundry run. The patch band hosts exactly one met1 track.
    if name == "TIE_X1":
        band = gdstk.rectangle((0, 1.06), (W, 1.26))
        for pname in list(pins):
            layer, poly = pins[pname]
            clipped = gdstk.boolean([poly], [band], "and")
            pins[pname] = (layer, clipped[0])
    pin_polys = [p for _, p in pins.values() if p is not None]
    rail_polys = [p for p in rails.values() if p is not None]
    obs_li = gdstk.boolean(li_polys, pin_polys, "not")
    obs_m1 = gdstk.boolean(m1_polys, pin_polys + rail_polys, "not")

    lef.append(f"MACRO {name}")
    lef.append(f"  CLASS {LEF_CLASS.get(name, 'CORE')} ;")
    lef.append("  ORIGIN 0 0 ;")
    lef.append(f"  SIZE {W:.3f} BY {H:.3f} ;")
    lef.append("  SYMMETRY X Y ;")
    lef.append("  SITE unithd ;")
    for pname, (layer, poly) in sorted(pins.items()):
        if poly is None:
            raise SystemExit(f"{name}: no polygon under label {pname}")
        use = "SIGNAL"
        d = "OUTPUT" if pname in OUTPUT_PINS else "INPUT"
        lef.append(f"  PIN {pname}")
        lef.append(f"    DIRECTION {d} ;")
        lef.append(f"    USE {use} ;")
        if name == "DIODE_X1" and pname == "DIODE":
            lef.append("    ANTENNADIFFAREA 0.4347 ;")
        lef.append("    PORT")
        lef.append(f"      LAYER {layer} ;")
        for x0, y0, x1, y1 in rects(poly):
            lef.append(f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;")
        lef.append("    END")
        lef.append(f"  END {pname}")
    for rname, poly in rails.items():
        x0, y0, x1, y1 = bbox(poly)
        use = "POWER" if rname == "VPWR" else "GROUND"
        lef.append(f"  PIN {rname}")
        lef.append("    DIRECTION INOUT ;")
        lef.append(f"    USE {use} ;")
        lef.append("    SHAPE ABUTMENT ;")
        lef.append("    PORT")
        lef.append("      LAYER met1 ;")
        lef.append(f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;")
        lef.append("    END")
        lef.append(f"  END {rname}")
    lef.append("  OBS")
    for layer, polys in (("li1", obs_li), ("met1", obs_m1)):
        if polys:
            lef.append(f"    LAYER {layer} ;")
            for p in polys:
                for x0, y0, x1, y1 in rects(p):
                    lef.append(f"      RECT {x0:.3f} {y0:.3f} "
                               f"{x1:.3f} {y1:.3f} ;")
    lef.append("  END")
    lef.append(f"END {name}")
    lef.append("")
    print(f"{name}: {len(pins)} pins, {len(obs_li)} li OBS, "
          f"{len(obs_m1)} met1 OBS, {W:.2f} x {H:.2f}")

lef.append("END LIBRARY")
(OUT / "own.lef").write_text("\n".join(lef))
merged_lib.write_gds(str(OUT / "own_cells.gds"))
print(f"\nwrote {OUT / 'own.lef'} and {OUT / 'own_cells.gds'}")
