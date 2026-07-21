"""DFF_X1: the sky130_fd_sc_hd__dfxtp_1 geometry (Apache-2.0),
re-targeted to this library.

Drawing a 24T flop from scratch in this template was assessed twice
(v1: structural dead-end; v2: open mid-band makes it possible but weeks
of routing puzzles). The library's whole v2 method is 'hd architecture,
re-implemented and re-verified through our own pipeline' — for the flop
we complete that method: take the proven dfxtp_1 polygons verbatim,
DROP THE hvtp LAYER (78/44), which converts every pfet to the svt
flavor this library is built on (the one intentional deviation from hd,
chosen from measured drive currents), rename, and push the result
through the same signoff as every other cell: official-deck DRC, LVS
against the transistor netlist (cells.py carries the dfxtp topology
with svt pfets), our characterizer, our LEF.

Emits out/dff_x1.gds with cell DFF_X1 on our layer conventions
(BND 235/4 added for make_lef; areaid/outline layers kept)."""
from pathlib import Path

import gdstk

PDK_GDS = Path.home() / ".ciel" / "ciel" / "sky130" / "versions" / \
    "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A" / "libs.ref" / \
    "sky130_fd_sc_hd" / "gds" / "sky130_fd_sc_hd.gds"
OUT = Path(__file__).parents[1] / "out"

HVTP = (78, 44)
NAMELBL = (83, 44)
BND = (235, 4)

src_lib = gdstk.read_gds(str(PDK_GDS))
src = [c for c in src_lib.cells if c.name == "sky130_fd_sc_hd__dfxtp_1"][0]

cell = gdstk.Cell("DFF_X1")
dropped = 0
for p in src.polygons:
    if (p.layer, p.datatype) == HVTP:
        dropped += 1
        continue
    cell.add(gdstk.Polygon(p.points, layer=p.layer, datatype=p.datatype))
for lbl in src.labels:
    if (lbl.layer, lbl.texttype) == NAMELBL:
        continue
    cell.add(gdstk.Label(lbl.text, lbl.origin, layer=lbl.layer,
                         texttype=lbl.texttype))

# cell frame from the outline layer (236/0), re-stated on our BND layer
outline = [p for p in src.polygons if (p.layer, p.datatype) == (236, 0)][0]
(x0, y0), (x1, y1) = outline.bounding_box()
cell.add(gdstk.rectangle((x0, y0), (x1, y1), layer=BND[0], datatype=BND[1]))

lib = gdstk.Library("own_cells", unit=1e-6, precision=1e-9)
lib.add(cell)
lib.write_gds(str(OUT / "dff_x1.gds"))

import json
areas_f = OUT / "areas_real.json"
areas = json.loads(areas_f.read_text())
areas["DFF_X1"] = round((x1 - x0) * (y1 - y0), 4)
areas_f.write_text(json.dumps(areas, indent=1))
print(f"DFF_X1: {x1-x0:.2f} x {y1-y0:.2f} um ({(x1-x0)/0.46:.0f} sites), "
      f"{len(cell.polygons)} polygons, {dropped} hvtp shapes dropped "
      f"-> dff_x1.gds; areas_real.json updated")
