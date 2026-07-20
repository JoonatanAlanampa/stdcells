# stdcells — roadmap

## Phase 1 ✅ device probe (2026-07-20)
Measured drives: nfet 477, pfet-svt 183, pfet-hvt 134 uA/um → Wp/Wn = 2.61,
svt PMOS chosen (drive over leakage — documented tradeoff).

## Phase 2 ✅ cell library at transistor level
10 cells (INV x1/2/4, BUF x2/4, NAND2/3, NOR2/3, DFF 22T master-slave).
Area = projected site model (finger folding, 0.46x2.72 um site) until the
layout phase.

## Phase 3 ✅ own characterizer → own.lib
~175 ngspice runs: input caps, 3x3 NLDM delay/transition per arc, DFF
clk→Q + setup bisection, leakage. Found: svt-PMOS leakage cost measured at
~200x on PMOS-off states (BUF 785 pW vs NAND2 3.5 pW) — the design choice,
quantified. DFF setup measured ≈ 0 ps (buffered internal clock delays the
capture edge — effectively negative setup; recorded as 0 in the .lib).

## Phase 4 ✅ synthesis PPA vs the taped-out chip's library
Same CORDIC-1 RTL, same yosys+ABC flow: own lib 1796 cells / 15446 um² /
773 ps critical path vs hd 969 / 8139 / 3525 ps. Fast, fat, leaky —
by design. Both meet 50 MHz. See out/REPORT.md.

## Phase 5 — cell LAYOUTS (STARTED 2026-07-20)
gdstk-generated GDS per cell on the sky130 hd grid (2.72 um rows, 0.46 um
sites): nwell/diff/poly/licon/li1/mcon/met1 + nsdm/psdm/npc. KLayout DRC
(sky130A_mr.drc) per cell; KLayout LVS vs the phase-2 netlists. Replaces
the projected areas with real ones.
- ✅ INV_X1 DRC-CLEAN (feol+beol+offgrid), 2nd iteration. 25 violations →
  0. Lessons: 3 sites impossible for folded cells (mid column must carry
  the Y strap; input contact needs its own column — hd's inv_2 is 4 sites
  for the same reason) → area model needs +1 site for folded cells; licon
  rows must sit on the 0.005 grid independently of diff centers; poly
  licon needs 0.19 to any diff (euclidean).
- TODO: remaining 9 cells (DFF is the boss fight); KLayout LVS device
  extraction vs own.spice; regenerate areas + re-run phases 3-4 with
  real numbers.

## Phase 5b ✅ LVS (2026-07-20) — all 7 cells MATCH; caught the BUF
## double-width nfet bug. Phase 5c ✅ LEF abstracts (make_lef.py).
## DFF: structural dead-end in this template (split-poly TG contacts) →
## HYBRID library for hardening (own combinational + hd dfxtp_1);
## custom DFF = stretch goal (wider template or met2).

## Phase 6 STATUS (2026-07-21): CI pipeline works END-TO-END through
## global routing (7 debug iterations: billing → image tag → node-in-
## container → linter → assign checker x2 → DRT). Blocker = LIBRARY
## ARCHITECTURE: DRT-0073 "no access point" on NAND2/NOR2 B pins — the
## top-region pads sit under the VPWR rail's met1 shadow (no via window).
## Analysis: with 0.85-um folded pdiff the mid-band is too narrow for any
## poly contact (pdiff licon clearance 0.19), flanks are unreachable
## through outer gates, higher straps merge with the mirrored neighbor.
## CONCLUSION: fat folded PMOS is incompatible with in-cell pin access —
## this is WHY hd sizes Wp<=1.0 single-finger with a wide mid-band.
## → V2 LIBRARY path: hd-like sizing (Wp 1.0/Wn 0.65, single finger),
## re-characterize + re-layout; v1 (symmetric-drive 2.61) stands as the
## documented fast/fat/leaky/unroutable-pins experiment.

## Phase 6 — LEF + OpenROAD hardening in CI
Abstract LEF from the layouts; GitHub Actions job (ubuntu + LibreLane or
bare OpenROAD) hardens the CORDIC-1 RTL with own.lib/own.lef on the TT 1x1
die size, 20 ns clock → post-P&R PPA vs the fabricated chip's 921 cells /
74% utilization. Decides whether the custom library fits a 1x1 tile.

## Phase 7 — silicon (the console path)
If 6 closes: the library is qualified for the chip-#4 console plan
(../devphys/PLAN.md grand-goal note); optionally tape the custom-cell
CORDIC itself on a future shuttle as the ultimate A/B experiment against
the 2026 tapeout.
