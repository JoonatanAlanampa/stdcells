"""Step 4: map the real CORDIC-1 RTL to BOTH libraries, compare PPA.

Same RTL (the taped-out sources, untouched), same yosys script, two
Liberty targets: our measured own.lib vs sky130_fd_sc_hd tt. Metrics:
mapped cell count, chip area (Liberty areas), ABC critical-path estimate.
Synthesis-level comparison — post-P&R numbers come from the CI hardening
phase later; the as-fabricated chip stats are quoted as reference.
"""
import re
from pathlib import Path

from common import OUT, HD_LIB, run_yosys

RTL = Path(__file__).resolve().parents[2] / "tt-cordic" / "src"
TOP = "tt_um_joonatanalanampa_cordic"
OWN = OUT / "own.lib"


def synth(lib, tag):
    script = f"""
read_verilog -sv "{RTL / 'cordic.sv'}" "{RTL / 'project.sv'}"
hierarchy -top {TOP}
flatten
synth -top {TOP}
dfflegalize -cell $_DFF_P_ x
dfflibmap -liberty "{lib}"
abc -liberty "{lib}" -script +strash;ifraig;scorr;dc2;dretime;strash;&get,-n;&dch,-f;&nf;&put;buffer;upsize;dnsize;stime,-p
opt_clean -purge
stat -liberty "{lib}"
"""
    log = run_yosys(script, tag)
    cells = {}
    area = None
    in_stat = False
    for line in log.splitlines():
        if "Printing statistics" in line:
            in_stat = True
            cells = {}
        if in_stat:
            m = re.match(r"\s+(\d+)\s+[\d.eE+]+\s+(\S+)\s*$", line)
            if m and not m.group(2).startswith("$") and m.group(2) != "cells":
                cells[m.group(2)] = int(m.group(1))
            m = re.search(r"Chip area for .*: ([\d.]+)", line)
            if m:
                area = float(m.group(1))
    delays = [float(m.group(1)) for m in
              re.finditer(r"[Dd]elay\s*=\s*([\d.]+)\s*ps", log)]
    return {"cells": cells, "n_cells": sum(cells.values()), "area": area,
            "delay_ps": max(delays) if delays else None}


own = synth(OWN, "synth_own")
hd = synth(HD_LIB, "synth_hd")

rep = []
rep.append("# CORDIC-1 synthesis PPA: own library vs sky130_fd_sc_hd\n")
rep.append("Same RTL (taped-out sources), same yosys flow, two Liberty "
           "targets.\nOwn-library timing/leakage: measured by our ngspice "
           "characterizer; own-library\nareas: REAL (DRC-clean layouts) for "
           "all cells except the DFF (projected).\nFoundry numbers: official "
           "PDK Liberty.\n")
rep.append("| metric | own library | sky130_fd_sc_hd | ratio own/hd |")
rep.append("|---|---|---|---|")
rep.append(f"| mapped cells | {own['n_cells']} | {hd['n_cells']} | "
           f"{own['n_cells']/hd['n_cells']:.2f} |")
rep.append(f"| chip area (um^2) | {own['area']:.0f} | {hd['area']:.0f} | "
           f"{own['area']/hd['area']:.2f} |")
d_o = own["delay_ps"] or float("nan")
d_h = hd["delay_ps"] or float("nan")
rep.append(f"| ABC critical path (ps) | {d_o:.0f} | {d_h:.0f} | "
           f"{d_o/d_h:.2f} |")
rep.append(f"| meets 50 MHz (20 ns) | {'YES' if d_o < 20000 else 'NO'} | "
           f"{'YES' if d_h < 20000 else 'NO'} | |")
rep.append("\n## Cell mix, own library\n")
for k, v in sorted(own["cells"].items(), key=lambda x: -x[1]):
    rep.append(f"- {k}: {v}")
rep.append("\n## Cell mix, sky130_fd_sc_hd (top 12)\n")
for k, v in sorted(hd["cells"].items(), key=lambda x: -x[1])[:12]:
    rep.append(f"- {k}: {v}")
rep.append("""
## Interpretation (v2 library)

v2 sizes like the foundry does (Wp=1.0/Wn=0.65 single-finger — the
architecture that detailed routing forced, see PLAN.md phase 6) and the
area penalty all but vanishes: ~1.1x hd for the same RTL, despite our
8-cell library being mapped against hd's hundreds (the 1.8x cell-count
ratio is small cells standing in for hd's complex gates — a21oi, mux2i,
xor2 — at nearly equal silicon). The critical path stays ~4x shorter at
synthesis level: that is the svt-PMOS choice (1.37x the hvt drive,
measured) plus zero-wire NLDM optimism; wire parasitics will shrink it
post-P&R. The cost is leakage on PMOS-off states (svt vs hd's hvt:
BUF_X2 ~1 nW vs single-digit pW for NAND/INV states, measured) and the
uncompensated series stacks (NAND2 251 ps vs INV_X1 195 ps mid-table) —
both characterized honestly, not hidden. Both libraries meet the
tapeout's 50 MHz with huge margin at this stage.
""")
rep.append("\n## Reference: the fabricated chip (TTSKY26c, commit b646d057)")
rep.append("921 cells post-P&R with sky130_fd_sc_hd, 74.0% utilization on a "
           "1x1 TinyTapeout tile\n(~160x100 um), 20 ns clock met. Post-P&R "
           "numbers for the own library follow in the\nCI hardening phase.")
text = "\n".join(rep)
(OUT / "REPORT.md").write_text(text)
print(text)
