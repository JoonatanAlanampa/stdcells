"""lib-v1.3: NLDM load-monotonicity guard. lib-v1.4: + the transition tables.

Delay must be non-decreasing in OUTPUT LOAD -- more load, slower output, longer
delay. That is physically unconditional, and a mis-measured .meas (a wrong-
crossing regression) almost always breaks it. This asserts it across every
cell_rise/cell_fall table of every corner and fails CI on a violation. It holds
today with zero exceptions, even through the light-load negatives (a delay that
is negative at 2 fF and positive at 25 fF is still *increasing* with load).

lib-v1.4 — WHY THIS FILE GREW. The sentence above ("a wrong-crossing regression
almost always breaks it") was true and this guard still missed defect M11 for
four library releases, because it parsed ONLY cell_rise/cell_fall. The wrong
crossing was in the OUTPUT-TRANSITION measurement, which no guard read. It now
checks all four tables for load-monotonicity, and additionally asserts that the
two transition tables are POSITIVE.

That positivity check is the one that would have caught M11 on day one, and it
is available for transitions precisely because it is NOT available for delay:
a 50-50 propagation delay may legitimately go negative in this library (the
early-trip paragraph below), so a negative number in the liberty could never be
the alarm on its own. A transition time is the interval between two thresholds
on the SAME monotone edge; it is a duration, and a negative duration is not a
measurement, it is a bug.

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
    r"(cell_rise|cell_fall|rise_transition|fall_transition)\s*\([^)]*\)\s*\{\s*"
    r'index_1\("([^"]*)"\);\s*index_2\("([^"]*)"\);\s*'
    r"values\(([^;]*)\)", re.S)

DELAY = ("cell_rise", "cell_fall")          # may be negative — see the docstring
TRANS = ("rise_transition", "fall_transition")   # durations: must be positive


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

    load_viol, neg_trans, slew_dips = [], [], 0
    n_delay = n_trans = 0
    for lib in libs:
        for name, tab, slews, loads, grid in parse(lib):
            n_delay += tab in DELAY
            n_trans += tab in TRANS
            for si in range(len(slews)):
                for li in range(1, len(loads)):        # LOAD: must be monotone
                    if grid[si][li] < grid[si][li - 1] - TOL_NS:
                        load_viol.append((lib.name, name, tab, slews[si],
                                          grid[si][li - 1], grid[si][li]))
            if tab in TRANS:
                # M11: a transition time is a duration on ONE monotone edge.
                # Negative means the .meas picked the wrong crossing, and STA
                # will clamp it to zero rather than reject it.
                for si in range(len(slews)):
                    for li in range(len(loads)):
                        if grid[si][li] <= 0.0:
                            neg_trans.append((lib.name, name, tab, slews[si],
                                              loads[li], grid[si][li]))
            if tab in DELAY:
                for li in range(len(loads)):
                    for si in range(1, len(slews)):    # SLEW: only counted
                        if grid[si][li] < grid[si - 1][li] - TOL_NS:
                            slew_dips += 1

    print(f"checked {len(libs)} corner liberties "
          f"({n_delay} delay + {n_trans} transition tables)")
    print(f"  slew-direction dips in delay (physical early-trip, reported): "
          f"{slew_dips}")
    print(f"  load-direction violations (must be 0): {len(load_viol)}")
    print(f"  non-positive transition values (must be 0): {len(neg_trans)}\n")

    if neg_trans:
        print("FAIL: transition time <= 0 — a duration between two thresholds "
              "on one monotone edge cannot be. This is defect M11's signature: "
              "a .meas qualified by crossing ordinal instead of direction. STA "
              "CLAMPS these to zero, so it will not complain for you:")
        for r in neg_trans[:20]:
            print(f"  {r[0]} {r[1]} {r[2]} (slew={r[3]} ns, load={r[4]} pF): "
                  f"{r[5]:.5f} ns")
        if len(neg_trans) > 20:
            print(f"  ... and {len(neg_trans) - 20} more")
        sys.exit(1)

    if load_viol:
        print("FAIL: value is non-monotonic in OUTPUT LOAD — physically "
              "impossible, so this is a characterization regression:")
        for r in load_viol:
            print(f"  {r[0]} {r[1]} {r[2]} (slew={r[3]} ns) load-nonmonotonic: "
                  f"{r[4]:.5f} -> {r[5]:.5f} ns")
        sys.exit(1)

    print("PASS: delay and transition monotonic in output load across all "
          "corners, and every transition positive. (Slew-direction dips are "
          "the documented physical early-trip.)")


if __name__ == "__main__":
    main()
