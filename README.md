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
5. *(next phases)* Cell layouts (gdstk) → DRC/LVS → LEF → OpenROAD
   hardening in CI → TinyTapeout.

## Results so far — CORDIC-1 synthesis PPA (phase 4)

Same taped-out RTL, same yosys+ABC flow, two Liberty targets:

| metric | **own library** | sky130_fd_sc_hd | ratio own/hd |
|---|---|---|---|
| mapped cells | 1783 | 969 | 1.84 |
| chip area (µm²; own = real layouts, DFF projected) | 17 686 | 8 139 | **2.17** |
| ABC critical path (ps) | **913** | 3 525 | **0.26** |
| meets the tapeout's 50 MHz | YES | YES | — |

The library is 8 cells (NOR3 and NAND3 were *dropped* after routing-cost
analysis — library design is economics; their instances remap to NAND2/NOR2
chains and the cost above is measured, not hidden). **All 7 combinational
cells have DRC-clean layouts** against the official `sky130A_mr.drc` deck;
the DFF layout is the remaining boss fight before LVS and P&R.

The measured library is **fast, fat and leaky — by design**: svt PMOS
(1.37× hvt drive, measured) sized at the measured 2.61 ratio makes every
gate a strong driver (~4× shorter critical path pre-wires) at 1.9× area
and ~200× worse PMOS-off leakage (785 pW vs 3.5 pW, measured). Details and
cell mix: [`out/REPORT.md`](out/REPORT.md). Every transistor's W/L:
[`out/own.spice`](out/own.spice) / rules in [`out/sizing.json`](out/sizing.json).

**Phase 5 first blood**: `INV_X1` layout
([`flow/layout.py`](flow/layout.py) → `out/inv_x1.gds`) is **DRC-clean**
against the official `sky130A_mr.drc` KLayout deck (FEOL+BEOL+offgrid),
second iteration. Lesson already banked: folded cells need 4 sites, not
the 3 the pre-layout area model assumed — real areas will be re-measured
from layouts.

## Status

- Phase 1–4: this repo, runs natively on Windows (ngspice + yosys from
  oss-cad-suite + the ciel-managed sky130A PDK).
- Area numbers before the layout phase are **projected** from a documented
  site-count model, clearly labeled; timing and leakage are measured.

## Requirements

sky130A PDK via `pip install ciel; ciel enable --pdk-family sky130 <ver>`;
ngspice (see `../devphys/tools`); oss-cad-suite yosys.
