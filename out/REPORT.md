# CORDIC-1 synthesis PPA: own library vs sky130_fd_sc_hd

Same RTL (taped-out sources), same yosys flow, two Liberty targets.
Own-library timing/leakage: measured by our ngspice characterizer; own-library
areas: REAL (DRC-clean layouts) for all cells except the DFF (projected).
Foundry numbers: official PDK Liberty.

| metric | own library | sky130_fd_sc_hd | ratio own/hd |
|---|---|---|---|
| mapped cells | 1782 | 969 | 1.84 |
| chip area (um^2) | 9104 | 8139 | 1.12 |
| ABC critical path (ps) | 907 | 3525 | 0.26 |
| meets 50 MHz (20 ns) | YES | YES | |

## Cell mix, own library

- NAND2_X1: 759
- NOR2_X1: 583
- INV_X1: 229
- DFF_X1: 191
- BUF_X2: 19
- BUF_X1: 1

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


## Reference: the fabricated chip (TTSKY26c, commit b646d057)
921 cells post-P&R with sky130_fd_sc_hd, 74.0% utilization on a 1x1 TinyTapeout tile
(~160x100 um), 20 ns clock met. Post-P&R numbers for the own library follow in the
CI hardening phase.