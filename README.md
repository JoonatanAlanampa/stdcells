# stdcells — CORDIC-1 on my own standard-cell library

Proof leg of the full-stack goal (see `../devphys`): re-implement the
taped-out CORDIC-1 chip using a **self-designed standard-cell library** —
every transistor chosen, sized from measured device behavior, characterized
with our own tooling — and compare PPA against the foundry library version
that went to fabrication (TTSKY26c, commit b646d057).

## Chain (all open source)

1. **Device probe** (`flow/device_probe.py`): measure sky130 n/pFET drive
   currents in ngspice → transistor sizing rules for the library.
2. **Cell netlists** (`flow/cells.py`): ~10 static-CMOS cells at
   transistor level (INV/BUF/NAND/NOR/DFF...), generated with the measured
   sizing.
3. **Own characterizer** (`flow/characterize.py`): ngspice transient
   measurements → NLDM Liberty (`out/own.lib`) + Verilog models. Delays,
   transitions, input caps, leakage, clk→Q, setup — all measured by us.
4. **Synthesis PPA comparison** (`flow/synth_compare.py`): yosys+ABC maps
   the REAL CORDIC-1 RTL (`../tt-cordic/src`) to (a) `own.lib` and
   (b) `sky130_fd_sc_hd tt` → `out/REPORT.md`.
5. **Cell layouts** (`flow/layout.py`, gdstk) → KLayout DRC
   (`flow/run_drc_all.py`, official `sky130A_mr.drc` deck) + LVS
   (`flow/run_lvs_all.py`, official `sky130.lvs` deck) → LEF abstracts
   (`flow/make_lef.py`, exact pin/OBS rectangle decompositions from the
   signoff GDS).
6. **Hardening** (`flow/make_hardening.py` → `harden/`): hybrid netlist
   (own combinational + hd dfxtp_1) placed & routed by LibreLane in CI
   on the TinyTapeout 1x1 tile budget.

## Results — CORDIC-1 synthesis PPA (library v2)

Same taped-out RTL, same yosys+ABC flow, two Liberty targets:

| metric | **own library v2** | sky130_fd_sc_hd | ratio own/hd |
|---|---|---|---|
| mapped cells | 1782 | 969 | 1.84 |
| chip area (µm²; own = real layouts, DFF projected) | 8 865 | 8 139 | **1.09** |
| ABC critical path (ps) | **919** | 3 525 | **0.26** |
| meets the tapeout's 50 MHz | YES | YES | — |

![the seven v2 cells](docs/cells_v2.png)

**v2 is the library the phase-6 routing failure demanded.** v1 sized for
symmetric edges (Wp = 2.61×Wn, measured) and proved DRC/LVS-clean — then
detailed routing rejected it: the fat folded PMOS closes the cell
mid-band, so input pins have no in-cell access point (DRT-0073; tag
`v1-symmetric-drive`, 2.17× hd area). v2 rebuilds every cell at
Wp=1.0/Wn=0.65 single-finger — the sky130_fd_sc_hd architecture, studied
from the PDK GDS and re-implemented generatively in `flow/layout.py` —
which opens the mid-band and puts **every pin at y≈1.19, clear of both
rail shadows**. All 7 cells came out DRC-clean in TWO iterations and
LVS-matched with zero netlist overrides (`flow/cells.py` now carries one
device per physical finger). Cell areas equal the foundry's exactly
(3/3/5/4/6/3/3 sites), and the full-design area penalty collapsed from
2.17× to 1.09×.

The library is 8 cells (NOR3 and NAND3 were *dropped* after routing-cost
analysis — library design is economics; their instances remap to NAND2/NOR2
chains and the cost above is measured, not hidden). LVS earned its keep in
v1 by catching a double-width NFET in the BUF cells that DRC could never
see; in v2 the extractor's multifinger merge is mirrored in the reference
netlists (`flow/run_lvs_all.py`).

## Hardening result (phase 6, v2)

LibreLane P&R of the hybrid netlist (our 7 cells + hd `dfxtp_1`) at 20 ns:
**routed with 0 violations — the v1 DRT-0073 pin-access blocker is dead**
— antenna-clean, and **timing met at every corner** (worst setup slack
+3.46 ns at ss/1.60 V, worst hold +0.11 ns at ff/1.95 V). The final GDS
passes the **full official KLayout deck (FEOL+BEOL+offgrid) with 0
violations** after one deterministic post-processing step:
`flow/heal_hvtp.py` bridges 36 corner-pinches in the foundry cells' hvtp
implant — an abutment case (hd band ending/starting at the same x in
mirrored rows) that only arises when hvtp-less custom cells interleave
with hd cells; the added implant is diamond-shaped, diff-free and
electrically inert, and the healed GDS is re-checked by the full deck.
Magic's DRC/LVS are demoted to warnings in `harden/config.json`: magic's
CIF read of GDS-only custom cells reports tens of thousands of phantom
errors on a layout the official KLayout deck proves clean (magic-native
cell views are future work if this library ever goes on a real shuttle).

**And it fits the tile — with every sequential and logic cell our own.**
With the die pinned to the exact TinyTapeout 1x1 footprint the
fabricated chip used (161.00 × 111.52 µm), the all-own netlist (1787 own
cells incl. 191 DFF_X1; only the 18 tie cells remain foundry) places,
routes, and passes the full signoff deck with 0 violations — final hold
slack +0.006 ns and setup +12.3 ns at the worst corners, 87% utilization.

Hard-won tuning lessons along the way: (1) a fast library makes hold
*overfixing* expensive — the default 0.1 ns resizer margin × our 171 ps
buffers meant hundreds of repair buffers; trim to ~0.005–0.02 ns.
(2) Our DFF_X1 is ~150 ps faster at clk→Q than the foundry flop, which
shortens every min-path and roughly quadruples hold repair — a fast flop
is not free. (3) The decisive lever was none of that: LibreLane's
default core margins (4/4/12/12 site-multiples) quietly spend 25% of a
1x1 tile; at 1/1/2/2 the core grows 13.5k → 16.9k µm². (4) A weak
"hold buffer" cell (BUF_X1, now in the library) does NOT win OpenROAD's
hold-buffer selection: the delay/area metric is evaluated at light load,
where a weak output stage has no delay advantage.

## Magic-native views

`flow/magic_views.tcl` + the `magic-views` CI workflow load the signoff
GDS into magic (LibreLane container), emit `.mag`/`.maglef` views, and
run magic's full per-cell DRC judged against a **foundry control group**:
hd's own `inv_1`/`dfxtp_1` are checked standalone first, and our cells
must show no rule category beyond theirs (the tap/latch-up rules every
tapless cell shows — resolved by tap cells at chip level). Status:
**PASS**. Getting there took two real fixes: the generated cells needed
the `areaid.standardc` (81/4) marker (magic relaxes contact-to-gate to
the 0.05 µm standard-cell rule only inside it), and magic caught a
genuine 45 nm contact-to-gate violation in BUF_X2 that the KLayout
deck's rule formulation misses — the two checkers are complementary,
which is exactly why shuttles run both.

## Custom DFF

`flow/make_dff.py` completes the library: it takes the silicon-proven
`dfxtp_1` polygons and **drops the hvtp implant layer**, which converts
every pfet to the svt flavor this library is built on — then the result
goes through the same signoff as every hand-generated cell: official-deck
DRC (clean), KLayout LVS against the 24T netlist transcribed in
`cells.py` (MATCH; the four 'special' pass nfets are normalized by the
deck itself), our characterizer (clk→Q 351 ps, setup ≈ 0, D pin 1.11 fF),
our LEF. The hybrid era is over.

**Sequential cells — a documented hybrid decision**: the transmission-gate
DFF needs split-poly columns whose lower gate contact has no legal landing
zone in this cell template (the same class of geometric dead-end that
eliminated NAND3, but structural). Hardening therefore uses a hybrid
library — our 7 verified combinational cells plus the foundry's
silicon-proven `sky130_fd_sc_hd__dfxtp_1` flop — which is standard
industry practice (flops are the most timing-critical, verification-heavy
cells). A fully custom DFF (wider template or met2 routing) remains the
stretch goal. LEF abstracts for P&R: `flow/make_lef.py` → `out/own.lef`,
derived from the exact LVS-verified polygons.

What v2 keeps from the measurements: **svt PMOS** (1.37× hvt drive,
measured) — the ~4× shorter synthesis-level critical path is that choice,
paid for in PMOS-off leakage (BUF_X2 ~1 nW vs single-digit pW NAND/INV
states, measured). What v2 gives up: symmetric edges (rise is ~1.7× slow)
and stack compensation (NAND2 251 ps vs INV_X1 195 ps mid-table) —
characterized honestly, not hidden. Details and cell mix:
[`out/REPORT.md`](out/REPORT.md). Every transistor's W/L:
[`out/own.spice`](out/own.spice) / rules in [`out/sizing.json`](out/sizing.json).

## Status

- Phases 1–5 (probe → cells → characterize → compare → layout/DRC/LVS/LEF)
  run natively on Windows (ngspice + oss-cad-suite yosys + KLayout + the
  ciel-managed sky130A PDK); phase 6 (P&R) runs in CI via the LibreLane
  container.
- All cell areas are REAL (signoff layouts) except the DFF, which is
  projected — hardening uses the foundry flop (hybrid decision above).
- Library v1 (symmetric-drive experiment) is preserved at tag
  `v1-symmetric-drive`; its post-mortem is in `PLAN.md`.

## Requirements

sky130A PDK via `pip install ciel; ciel enable --pdk-family sky130 <ver>`;
ngspice (see `../devphys/tools`); oss-cad-suite yosys.
