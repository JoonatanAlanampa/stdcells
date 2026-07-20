"""The library: ~10 static-CMOS cells at transistor level.

Every size traces to out/sizing.json (measured drive currents): WN_X1 =
0.65 um, WP = ratio*WN for symmetric rise/fall, L = 0.15 um, series stacks
width-compensated by the stack depth. Area is PROJECTED (pre-layout) from
a finger/site model: fingers = ceil(W / W_max_per_row), cell sites =
1 + max(sum p-fingers, sum n-fingers), site = 0.46 x 2.72 um (sky130 hd
grid) — labeled as an estimate until the layout phase replaces it.
"""
import json
from pathlib import Path

SIZING = json.loads((Path(__file__).parents[1] / "out" / "sizing.json")
                    .read_text())
L = SIZING["L"]
WN = SIZING["WN_X1"]
WP = round(WN * SIZING["WP_over_WN"], 2)
NMOD = SIZING["nfet_model"]
PMOD = SIZING["pfet_model"]
WMAX_P, WMAX_N = 1.0, 0.65          # max unfolded width per sky130 hd row
SITE_AREA = 0.46 * 2.72             # um^2


def _fingers(w, wmax):
    import math
    return math.ceil(round(w / wmax, 3))


class Cell:
    def __init__(self, name, inputs, output, function, mos, clocked=None):
        """mos: list of (type 'n'/'p', drain, gate, source, W)."""
        self.name, self.inputs, self.output = name, inputs, output
        self.function, self.mos, self.clocked = function, mos, clocked
        pf = sum(_fingers(w, WMAX_P) for t, *_ , w in
                 [(t, d, g, s, w) for t, d, g, s, w in mos] if t == "p")
        nf = sum(_fingers(w, WMAX_N) for t, d, g, s, w in mos if t == "n")
        self.sites = 1 + max(pf, nf)
        self.area = round(self.sites * SITE_AREA, 4)

    def spice(self):
        lines = [f".subckt {self.name} " +
                 " ".join(self.inputs + [self.output]) + " vdd vss"]
        for i, (t, d, g, s, w) in enumerate(self.mos):
            bulk, model = ("vdd", PMOD) if t == "p" else ("vss", NMOD)
            lines.append(f"xm{i} {d} {g} {s} {bulk} {model} w={w} l={L}")
        lines.append(".ends")
        return "\n".join(lines)


def inv(name, scale):
    return Cell(name, ["A"], "Y", "(!A)",
                [("p", "Y", "A", "vdd", round(WP * scale, 2)),
                 ("n", "Y", "A", "vss", round(WN * scale, 2))])


def buf(name, scale):
    return Cell(name, ["A"], "Y", "A",
                [("p", "yb", "A", "vdd", WP), ("n", "yb", "A", "vss", WN),
                 ("p", "Y", "yb", "vdd", round(WP * scale, 2)),
                 ("n", "Y", "yb", "vss", round(WN * scale, 2))])


def nandN(name, n, stack_comp):
    """Layout reality (phase 5) capped the stack compensation: NAND2 keeps
    the full 2x (two 0.65 um chain fingers); NAND3 is de-rated to 2x as
    well — 3x would need 1.95 um = three chains, whose third input cannot
    be routed in-row. The slower NAND3 fall is measured, not hidden."""
    ins = ["A", "B", "C"][:n]
    mos = [("p", "Y", x, "vdd", WP) for x in ins]
    node = "Y"
    wn = round(WN * stack_comp, 2)
    for i, x in enumerate(ins):
        nxt = "vss" if i == n - 1 else f"m{i}"
        mos.append(("n", node, x, nxt, wn))
        node = nxt
    return Cell(name, ins, "Y", "(!(" + "&".join(ins) + "))", mos)


def norN(name, n, stack_comp):
    """NOR2 de-rated to NO pull-up stack compensation: 2x would need
    3.4 um series pfets (four folded chains) that explode the cell. The
    ~2x slower rise is a documented, characterized design decision."""
    ins = ["A", "B", "C"][:n]
    wp = round(WP * stack_comp, 2)
    mos = []
    node = "vdd"
    for i, x in enumerate(ins):
        nxt = "Y" if i == n - 1 else f"m{i}"
        mos.append(("p", nxt, x, node, wp))
        node = nxt
    mos += [("n", "Y", x, "vss", WN) for x in ins]
    return Cell(name, ins, "Y", "(!(" + "|".join(ins) + "))", mos)


def dff(name):
    """Positive-edge master-slave DFF, transmission gates, isolated output
    inverter. ~22 transistors; feedback inverters weak (0.42/0.55)."""
    WFN, WFP = 0.42, 0.55
    WTN, WTP = 0.65, 1.05
    m = [
        # local clock buffers: CLK -> cn -> cp
        ("p", "cn", "CLK", "vdd", WP), ("n", "cn", "CLK", "vss", WN),
        ("p", "cp", "cn", "vdd", WP), ("n", "cp", "cn", "vss", WN),
        # master pass gate: D -> m1, transparent when CLK=0
        ("n", "D", "cn", "m1", WTN), ("p", "D", "cp", "m1", WTP),
        # master inverter m1 -> m2, weak feedback m2 -> mfb -> (TG on CLK=1) m1
        ("p", "m2", "m1", "vdd", WP), ("n", "m2", "m1", "vss", WN),
        ("p", "mfb", "m2", "vdd", WFP), ("n", "mfb", "m2", "vss", WFN),
        ("n", "mfb", "cp", "m1", WFN), ("p", "mfb", "cn", "m1", WFP),
        # slave pass gate: m2 -> s1, transparent when CLK=1
        ("n", "m2", "cp", "s1", WTN), ("p", "m2", "cn", "s1", WTP),
        # slave inverter s1 -> s2, weak feedback s2 -> sfb -> (TG on CLK=0) s1
        ("p", "s2", "s1", "vdd", WP), ("n", "s2", "s1", "vss", WN),
        ("p", "sfb", "s2", "vdd", WFP), ("n", "sfb", "s2", "vss", WFN),
        ("n", "sfb", "cn", "s1", WFN), ("p", "sfb", "cp", "s1", WFP),
        # isolated output inverter: s1 (= !Q internal) ... Q = !s1
        ("p", "Q", "s1", "vdd", WP), ("n", "Q", "s1", "vss", WN),
    ]
    return Cell(name, ["D", "CLK"], "Q", None, m, clocked="CLK")


# NOR3 dropped from the library after phase-5 cost analysis: its series
# pull-up would need 5.1 um of folded pfet for 11 mapped instances — ABC
# remaps those to NOR2/INV at negligible cost. Library design is economics.
# NAND3 also dropped after phase-5 routing analysis: its inner-solo input
# has no legal in-row join (see layout.py) — 157 instances remap to NAND2
# chains and the measured cost is part of the result.
LIBRARY = [
    inv("INV_X1", 1), inv("INV_X2", 2), inv("INV_X4", 4),
    buf("BUF_X2", 2), buf("BUF_X4", 4),
    nandN("NAND2_X1", 2, 2),
    norN("NOR2_X1", 2, 1),
    dff("DFF_X1"),
]

if __name__ == "__main__":
    for c in LIBRARY:
        print(f"{c.name:9s} {len(c.mos):2d}T  {c.sites} sites  "
              f"{c.area:6.3f} um2  fn={c.function}")
    # the human-readable W/L record: every transistor of every cell
    out = Path(__file__).parents[1] / "out" / "own.spice"
    hdr = (f"* own standard-cell library — transistor-level netlists\n"
           f"* sizing from measured drives (out/sizing.json): L={L}um, "
           f"WN_X1={WN}um, WP={WP}um (={SIZING['WP_over_WN']}x WN)\n"
           f"* nfet: {NMOD}   pfet: {PMOD}\n\n")
    out.write_text(hdr + "\n\n".join(c.spice() for c in LIBRARY) + "\n")
    print(f"\nwrote {out}")
