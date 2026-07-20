# CORDIC-1 synthesis PPA: own library vs sky130_fd_sc_hd

Same RTL (taped-out sources), same yosys flow, two Liberty targets.
Own-library timing/leakage: measured by our ngspice characterizer; own-library
areas: REAL (DRC-clean layouts) for INV_X1/X2/X4, NAND2, NOR2 — projected site
model for the rest. Foundry numbers: official PDK Liberty.

| metric | own library | sky130_fd_sc_hd | ratio own/hd |
|---|---|---|---|
| mapped cells | 1691 | 969 | 1.75 |
| chip area (um^2) | 16481 | 8139 | 2.02 |
| ABC critical path (ps) | 724 | 3525 | 0.21 |
| meets 50 MHz (20 ns) | YES | YES | |

## Cell mix, own library

- NAND2_X1: 581
- INV_X1: 322
- NOR2_X1: 304
- NAND3_X1: 259
- DFF_X1: 191
- BUF_X2: 31
- BUF_X4: 2
- INV_X4: 1

## Cell mix, sky130_fd_sc_hd (top 12)

- sky130_fd_sc_hd__dfxtp_1: 191
- sky130_fd_sc_hd__nor2_1: 177
- sky130_fd_sc_hd__o21ai_0: 117
- sky130_fd_sc_hd__a21oi_1: 88
- sky130_fd_sc_hd__nand2_1: 51
- sky130_fd_sc_hd__a22oi_1: 41
- sky130_fd_sc_hd__inv_1: 23
- sky130_fd_sc_hd__xnor2_1: 23
- sky130_fd_sc_hd__nor3_1: 20
- sky130_fd_sc_hd__xor2_1: 19
- sky130_fd_sc_hd__mux2i_1: 18
- sky130_fd_sc_hd__lpflow_clkbufkapwr_1: 17

## Interpretation

The library we measured is FAST, FAT and LEAKY — exactly where our design
choices put it: svt PMOS (1.37x the hvt drive) sized 2.61x for symmetric
edges makes every gate a strong driver (critical path ~4x shorter at
synthesis level, before wire parasitics shrink that gap), at the cost of
1.9x area and ~200x worse leakage on PMOS-off states (measured: BUF 785 pW
vs NAND2 3.5 pW). The foundry library wins on balance; ours wins the drag
race. Both meet the tapeout's 50 MHz with huge margin at this stage.


## Reference: the fabricated chip (TTSKY26c, commit b646d057)
921 cells post-P&R with sky130_fd_sc_hd, 74.0% utilization on a 1x1 TinyTapeout tile
(~160x100 um), 20 ns clock met. Post-P&R numbers for the own library follow in the
CI hardening phase.