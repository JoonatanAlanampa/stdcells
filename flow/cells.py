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
        for i, (t, d, g, s, w, *m) in enumerate(self.mos):
            bulk, model = ("vdd", PMOD) if t == "p" else ("vss", NMOD)
            if m:                       # explicit model override (DFF pass
                model = m[0]            # nfets are the 'special' flavor)
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


SPECIAL_N = "sky130_fd_pr__special_nfet_01v8"


def dff(name):
    """DFF_X1: the dfxtp_1 topology (24T) with svt pfets — matching the
    layout make_dff.py produces (hd geometry minus the hvtp layer).
    Master-slave with transmission-gate inputs and clocked-inverter
    feedback; local two-stage clock buffer; isolated output inverter.
    The four pass nfets are the PDK's 'special' low-leakage flavor, as
    drawn. Widths are dfxtp_1's own (documented deviation: the pfets
    are ~1.37x stronger here because svt — measured, characterized)."""
    m = [
        # clock: CLK -> cn -> cp
        ("n", "cn", "CLK", "vss", 0.42), ("p", "cn", "CLK", "vdd", 0.64),
        ("n", "vss", "cn", "cp", 0.42), ("p", "vdd", "cn", "cp", 0.64),
        # input inverter D -> db
        ("p", "vdd", "D", "db", 0.42), ("n", "vss", "D", "db", 0.42),
        # master TG: db -> m1 (transparent CLK=0)
        ("n", "db", "cn", "m1", 0.36, SPECIAL_N), ("p", "db", "cp", "m1", 0.42),
        # master inverter m1 -> m2
        ("p", "vdd", "m1", "m2", 0.75), ("n", "vss", "m1", "m2", 0.64),
        # master feedback: clocked inverter m2 -> m1 (active CLK=1)
        ("n", "mfn", "m2", "vss", 0.42),
        ("n", "m1", "cp", "mfn", 0.36, SPECIAL_N),
        ("p", "mfp", "m2", "vdd", 0.42), ("p", "m1", "cn", "mfp", 0.42),
        # slave TG: m2 -> s1 (transparent CLK=1)
        ("p", "m2", "cn", "s1", 0.42), ("n", "m2", "cp", "s1", 0.36, SPECIAL_N),
        # slave inverter s1 -> s2
        ("n", "s2", "s1", "vss", 0.65), ("p", "s2", "s1", "vdd", 1.0),
        # slave feedback: clocked inverter s2 -> s1 (active CLK=0)
        ("n", "sfn", "s2", "vss", 0.42),
        ("n", "s1", "cn", "sfn", 0.36, SPECIAL_N),
        ("p", "s1", "cp", "sfp", 0.42), ("p", "sfp", "s2", "vdd", 0.42),
        # output inverter s2 -> Q
        ("p", "vdd", "s2", "Q", 1.0), ("n", "vss", "s2", "Q", 0.65),
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
