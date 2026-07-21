"""The library v2: 8 static-CMOS cells at transistor level.

v2 sizing (the phase-6 lesson): WP = 1.0 um, WN = 0.65 um, SINGLE-FINGER
devices, no folding, no stack compensation. v1 sized WP = 2.61x WN from
measured drive currents for symmetric edges; the resulting 0.85-um folded
PMOS fingers closed the cell mid-band and left no legal in-cell landing
for input pins (detailed routing DRT-0073). The cap keeps the mid-band
open; the slower rise and the 2x-slower series edges are characterized
honestly, not hidden. Drive scaling is by parallel fingers (X2 = 2, X4 =
4), each at the capped width — mos lists carry ONE ENTRY PER FINGER so
the netlist is topologically identical to the layout (LVS needs no
overrides).

Area is PROJECTED (pre-layout) as 1 + max(p-fingers, n-fingers) sites
(min 3: a single-finger cell still needs contact-gate-contact plus the
pad column), site = 0.46 x 2.72 um; out/areas_real.json replaces these
after the layout phase.
"""
import json
from pathlib import Path

SIZING = json.loads((Path(__file__).parents[1] / "out" / "sizing.json")
                    .read_text())
L = SIZING["L"]
WN = SIZING["WN_X1"]
WP = SIZING["WP_X1"]
NMOD = SIZING["nfet_model"]
PMOD = SIZING["pfet_model"]
SITE_AREA = 0.46 * 2.72             # um^2


class Cell:
    def __init__(self, name, inputs, output, function, mos, clocked=None):
        """mos: list of (type 'n'/'p', drain, gate, source, W) — one entry
        per physical finger."""
        self.name, self.inputs, self.output = name, inputs, output
        self.function, self.mos, self.clocked = function, mos, clocked
        pf = sum(1 for t, *_ in mos if t == "p")
        nf = sum(1 for t, *_ in mos if t == "n")
        self.sites = max(3, 1 + max(pf, nf))
        self.area = round(self.sites * SITE_AREA, 4)

    def spice(self):
        lines = [f".subckt {self.name} " +
                 " ".join(self.inputs + [self.output]) + " vdd vss"]
        for i, (t, d, g, s, w) in enumerate(self.mos):
            bulk, model = ("vdd", PMOD) if t == "p" else ("vss", NMOD)
            lines.append(f"xm{i} {d} {g} {s} {bulk} {model} w={w} l={L}")
        lines.append(".ends")
        return "\n".join(lines)


def inv(name, fingers):
    m = []
    for _ in range(fingers):
        m += [("p", "Y", "A", "vdd", WP), ("n", "Y", "A", "vss", WN)]
    return Cell(name, ["A"], "Y", "(!A)", m)


def buf(name, s2_fingers):
    m = [("p", "yb", "A", "vdd", WP), ("n", "yb", "A", "vss", WN)]
    for _ in range(s2_fingers):
        m += [("p", "Y", "yb", "vdd", WP), ("n", "Y", "yb", "vss", WN)]
    return Cell(name, ["A"], "Y", "A", m)


def nandN(name, n):
    """No stack compensation (v2): the series nfets stay at WN — the same
    choice hd makes, and the reason its nand2 fits 3 sites. The ~2x slower
    fall is measured by the characterizer, not hidden."""
    ins = ["A", "B", "C"][:n]
    mos = [("p", "Y", x, "vdd", WP) for x in ins]
    node = "Y"
    for i, x in enumerate(ins):
        nxt = "vss" if i == n - 1 else f"m{i}"
        mos.append(("n", node, x, nxt, WN))
        node = nxt
    return Cell(name, ins, "Y", "(!(" + "&".join(ins) + "))", mos)


def norN(name, n):
    """Series pull-up at WP, uncompensated (v2) — same rationale."""
    ins = ["A", "B", "C"][:n]
    mos = []
    node = "vdd"
    for i, x in enumerate(ins):
        nxt = "Y" if i == n - 1 else f"m{i}"
        mos.append(("p", nxt, x, node, WP))
        node = nxt
    mos += [("n", "Y", x, "vss", WN) for x in ins]
    return Cell(name, ins, "Y", "(!(" + "|".join(ins) + "))", mos)


def dff(name):
    """Positive-edge master-slave DFF, transmission gates, isolated output
    inverter. ~22 transistors; feedback inverters weak (0.42/0.55).
    Characterization-only in v2: the hardened netlist uses hd dfxtp_1
    (the custom-DFF layout remains the documented stretch goal)."""
    WFN, WFP = 0.42, 0.55
    WTN, WTP = 0.65, 1.0
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


# NAND3/NOR3 stay dropped (v1 economics + routing analysis): ABC remaps
# their instances to NAND2/NOR2 chains and the measured cost is part of
# the PPA result.
LIBRARY = [
    inv("INV_X1", 1), inv("INV_X2", 2), inv("INV_X4", 4),
    buf("BUF_X2", 2), buf("BUF_X4", 4),
    nandN("NAND2_X1", 2),
    norN("NOR2_X1", 2),
    dff("DFF_X1"),
]

if __name__ == "__main__":
    for c in LIBRARY:
        print(f"{c.name:9s} {len(c.mos):2d}T  {c.sites} sites  "
              f"{c.area:6.3f} um2  fn={c.function}")
    # the human-readable W/L record: every transistor of every cell
    out = Path(__file__).parents[1] / "out" / "own.spice"
    hdr = (f"* own standard-cell library v2 — transistor-level netlists\n"
           f"* sizing: L={L}um, WN={WN}um, WP={WP}um single-finger "
           f"(routability cap; measured symmetric ratio "
           f"{SIZING['WP_over_WN_measured']}x — see sizing.json)\n"
           f"* nfet: {NMOD}   pfet: {PMOD}\n\n")
    out.write_text(hdr + "\n\n".join(c.spice() for c in LIBRARY) + "\n")
    print(f"\nwrote {out}")
