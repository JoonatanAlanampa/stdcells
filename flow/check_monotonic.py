"""lib-v1.3: NLDM load-monotonicity guard.

Delay must be non-decreasing in OUTPUT LOAD -- more load, slower output, longer
delay. That is physically unconditional, and a mis-measured .meas (a wrong-
crossing regression) almost always breaks it. This asserts it across every
cell_rise/cell_fall table of every corner and fails CI on a violation. It holds
today with zero exceptions, even through the light-load negatives (a delay that
is negative at 2 fF and positive at 25 fF is still *increasing* with load).

It deliberately does NOT require monotonicity in INPUT SLEW, because for this
library that would be wrong. These cells are asymmetric by design (WP 1.0 um >
WN 0.65 um -- the routability sizing; folding a symmetric PMOS closed the cell,
see cells.py), so their switching threshold sits off Vdd/2 and the 50-50
propagation delay *shrinks* as the input ramp slows (the output trips before the
input reaches 50 %). This "early trip" is real and pervasive, not a corner
artifact: e.g. BUF_X1 cell_rise at ff goes 67 -> 26 ps from the 0.05 to 0.3 ns
slew, and INV_X4 cell_fall at ff/1.5 ns/2 fF is -96 ps (output-50 % crossed 96 ps
BEFORE input-50 %, input still 0.90 V < Vdd/2 -- waveform-confirmed). Liberty
permits negative delays; this library does not clamp measured data, and forcing
slew-monotonicity would fabricate it. It is present since lib-v1.0 and does not
affect signoff: load-monotonicity (the property STA leans on for a fixed driver)
holds, and lib-v1.0/v1.1/v1.2 all closed green. The slew-direction dips are
REPORTED here for visibility, never failed.

Usage:  python check_monotonic.py
"""
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"

TOL_NS = 0.003           # 3 ps: below the 2 ps tran timestep resolution -> noise

NUM = re.compile(r"-?\d+\.\d+")
CELL = re.compile(r"cell \((\w+)\)")
TAB = re.compile(
    r"(cell_rise|cell_fall)\s*\([^)]*\)\s*\{\s*"
    r'index_1\("([^"]*)"\);\s*index_2\("([^"]*)"\);\s*'
    r"values\(([^;]*)\)", re.S)


def parse(path):
    """-> [(cell, table, slews[], loads[], grid[slew][load])] in ns."""
    text = path.read_text()
    tables, cells = [], list(CELL.finditer(text))
    for i, cm in enumerate(cells):
        name = cm.group(1)
        end = cells[i + 1].start() if i + 1 < len(cells) else len(text)
        for tm in TAB.finditer(text[cm.end():end]):
            slews = [float(x) for x in NUM.findall(tm.group(2))]
            loads = [float(x) for x in NUM.findall(tm.group(3))]
            grid = [[float(x) for x in NUM.findall(row)]
                    for row in tm.group(4).split('"') if NUM.search(row)]
            tables.append((name, tm.group(1), slews, loads, grid))
    return tables


def main():
    libs = sorted(p for p in OUT.glob("own_*C_*v*.lib")
                  if "hardening" not in p.name)
    if not libs:
        sys.exit("FAIL: no per-corner liberty files in out/ — run characterize.py")

    load_viol, slew_dips = [], 0
    for lib in libs:
        for name, tab, slews, loads, grid in parse(lib):
            for si in range(len(slews)):
                for li in range(1, len(loads)):        # LOAD: must be monotone
                    if grid[si][li] < grid[si][li - 1] - TOL_NS:
                        load_viol.append((lib.name, name, tab, slews[si],
                                          grid[si][li - 1], grid[si][li]))
            for li in range(len(loads)):
                for si in range(1, len(slews)):        # SLEW: only counted
                    if grid[si][li] < grid[si - 1][li] - TOL_NS:
                        slew_dips += 1

    print(f"checked {len(libs)} corner liberties (cell_rise/cell_fall)")
    print(f"  slew-direction dips (physical early-trip, reported): {slew_dips}")
    print(f"  load-direction violations (must be 0): {len(load_viol)}\n")

    if load_viol:
        print("FAIL: delay is non-monotonic in OUTPUT LOAD — physically "
              "impossible, so this is a characterization regression:")
        for r in load_viol:
            print(f"  {r[0]} {r[1]} {r[2]} (slew={r[3]} ns) load-nonmonotonic: "
                  f"{r[4]:.5f} -> {r[5]:.5f} ns")
        sys.exit(1)

    print("PASS: delay monotonic in output load across all corners. "
          "(Slew-direction dips are the documented physical early-trip.)")


if __name__ == "__main__":
    main()
