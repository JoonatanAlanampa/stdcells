# v3 Phase 2 — devphys as an independent cross-check of the OWN cells (RESULT, 2026-07-24)

**Phase 2 on the reframed footing (flow/offbin/RESULT.md): devphys is not a
gap-filler for geometries the foundry forbids — it is an INDEPENDENT
from-physics CROSS-CHECK of the rectangular cells we actually build. This phase
(1) closes the device V3-PLAN Phase 2 suggested building on — a longer-L
"geometric-hvt" NMOS — as a fourth dead-end, then (2) executes the real
deliverable: devphys stages 4–5 vs BSIM on the library's own manufacturable
NMOS, and a re-harden of CORDIC-1 on the cross-checked liberty vs lib-v1.x.**

Repro at the bottom. All BSIM runs are native ngspice; the devphys side reads
committed DEVSIM solves (no DEVSIM run here, no devphys edits).

---

## 1. The suggested vehicle is a dead-end: longer-L is NOT geometric-hvt on sky130

`longL_gate.py` (BSIM tt, W = 0.65 µm = the library WN). A longer channel is the
natural "no hvt NMOS exists → control leakage with geometry" play. It does not
work, for the same structural reason the three exotic targets closed: **sky130's
halo/pocket implants are engineered so leakage is ~L-independent.**

| L (µm) | Vt_lin | DIBL (mV) | Ion (µA) | Ioff (pA) 25 °C | Ioff (pA) 100 °C |
|---|---|---|---|---|---|
| 0.15 | 0.681 | 83 | 296.2 | 1.92 | 10.26 |
| 0.18 | 0.642 | 71 | 273.4 | 1.90 | 8.63 |
| 0.25 | 0.612 | 43 | 230.4 | 1.91 | 8.50 |
| 0.35 | 0.592 | 31 | 187.7 | 1.92 | 8.28 |
| 0.50 | 0.588 | 15 | 142.1 | 1.88 | 5.90 |

- Longer L **suppresses DIBL** (83 → 15 mV) — but the halo/RSCE implants **lower
  Vt by the same amount**, so the two cancel: at 25 °C **Ioff is flat (~1.9 pA)**
  while Ion falls ×0.48. The leakage/speed figure of merit **Ion/Ioff only
  worsens** (best-vs-L=0.15 = ×1.00).
- At 100 °C longer L does cut Ioff, but Ion drops harder, so **Ion/Ioff still
  does not improve** for any useful step (best = ×1.09, the marginal 0.15→0.18
  bump). Not a lever.

**A longer-L cell set would also cost a full hand-redraw of every cell** (the N
and P share one vertical poly gate in `layout.py`, so longer L is not a
parameter tweak) — for a strictly-worse library. Closed.

**The other named geometric lever — STACKING — is real** (unlike longer-L): a
2-high nfet stack cuts Ioff **3.5× at 100 °C** (Ion/Ioff ×2.05). But it wins only
at the hot corner (×1.0 at 25 °C), costs ~½ the drive, and is a topology the
library **already uses** in NAND2/NOR2. So it is not a new-cell opportunity
either — it reinforces that the honest Phase 2 is the cross-check, not an
hvt cell set.

## 2. The real deliverable: devphys stages 4–5 cross-check the OWN NMOS

`crosscheck_devices.py`. Same geometry, two fully independent characterizations
of the library's pull-down device **nfet_01v8 W = 0.65 µm, L = 0.15 µm**:
BSIM (ngspice, what lib-v1.x is built on) vs devphys (DEVSIM TCAD calibrated to
measured 25×25 silicon, transferred to L = 0.15 µm — stage 4c short-channel +
stage 4d S/D resistance — width-scaled per-µm × 0.65).

| metric | devphys | BSIM | Δ |
|---|---|---|---|
| **Ion** (Vg=Vd=1.8, µA) | 309.2 | 295.3 | **+4.7 %** |
| Ilin (Vg=1.8, Vd=0.1, µA) | 74.7 | 66.1 | +13.0 % |
| Vt (max-gm, V) | 0.714 | 0.735 | −2.9 % |
| DIBL (mV) | 121 | 83 | +46 % |

- **Headline: Ion agrees to +4.7 % from fully independent physics.** devphys
  reproduces the drive that sets the cells' fall delay without ever seeing a BSIM
  parameter. That is the reframe's deliverable on a real cell device.
- **Honest, not hidden:** the linear drive is +13 % high even after the stage-4d
  Rsd correction (the 2D scalar-W model still lacks the n+ heavy-doping mobility
  roll-off; it bites at Vd=0.1 and far less at the Vd=1.8 operating point), and
  DIBL is over-predicted +46 % (a known limit of the 2D electrostatics / the
  single-knob halo proxy — direction right, magnitude high).
- **PMOS (pfet_01v8 W = 1.0 µm) is deferred**: the L = 0.15 µm PMOS solve
  (`08_pfet/pfet_short_results.npz`) does not yet exist — it is the devphys
  session's in-flight **stage-8** work (short-L PMOS biased-sweep convergence →
  compose-INV). This cross-check consumes it when it lands; the pull-up (rise)
  arcs stay on BSIM and are flagged until then. We do not run or edit devphys
  here (parallel-session board discipline).

## 3. Cross-checked liberty + re-harden CORDIC-1 vs lib-v1.x

`xcheck_liberty.py` → `out/own_devphys_xcheck.lib`. A **first-order device-drive
cross-check** (explicitly not a re-characterization): to first order delay is
drive-limited (t ≈ C·Vdd/I), so the pull-down (`cell_fall` / `fall_transition`)
arcs of the signed-off BSIM `own.lib` are scaled by 1/k_N = 1/1.047 = **0.955**
(−4.5 %); `cell_rise`/`rise_transition` stay on BSIM (PMOS pending stage-8);
caps, power, leakage, areas, setup/hold untouched. 22 fall tables scaled.

`reharden_compare.py` synthesizes CORDIC-1 (`tt_um_joonatanalanampa_cordic`)
against both libraries:

| | BSIM lib-v1.x | devphys-cross-checked |
|---|---|---|
| INV_X1 / NAND2_X1 / NOR2_X1 | 229 / 759 / 583 | 229 / 759 / 583 |
| BUF_X2 / DFF_X1 / TIE_X1 | 25 / 191 / 18 | 25 / 191 / 18 |
| **total cells** | **1805** | **1805** |
| **total cell area** | **9913.3 µm²** | **9913.3 µm²** |
| gate netlist | — | **identical** |

**The devphys-cross-checked library hardens CORDIC-1 to the same cells, same
count, same area → the same silicon shape** (technology mapping is structural,
insensitive to a 4.5 % delay shift; LEF/GDS are unchanged, so a CI GDS harden
would be byte-identical — which is why it is not spun here). The **only PPA
delta is the timing band**: every pull-down (fall) path is 4.5 % faster under
devphys's independently-derived drive; pull-up paths on BSIM pending stage-8.

That band — not a new floorplan — is the whole comparison, and it is the
independent-physics cross-check made concrete on the hardened design:
**own physics → own cells → silicon, cross-checked to +4.7 %.**

## Honest limitations (what a reviewer should push on)

- The scaled liberty is a **sensitivity view**: it treats delay as purely
  drive-limited and scales every fall entry uniformly, so it over-scales the
  light-load intrinsic part and ignores the slew-shape / input-cap BSIM bakes
  into the NLDM (devphys does not re-derive those). Good to first order at the
  ~5 % agreement level; it is not a signoff library.
- devphys's linear-region (+13 %) and DIBL (+46 %) gaps are real model limits
  (Rsd mobility roll-off; 2D halo proxy). The Ion agreement is the strong claim;
  the sub-threshold/linear agreement is weaker and reported as such.
- Half the device story (PMOS pull-up) is gated on the devphys session's
  stage-8. Until it lands, "cross-checked" means the NMOS pull-down half.

## Consequence for V3-PLAN

Phase 2 is delivered on the cross-check footing, NOT as an hvt cell set:
- longer-L geometric-hvt = the **4th closed** "geometric leakage control" target
  (after narrow-width, annular, off-bin rectangular);
- the reframe is demonstrated end-to-end on a real cell device and carried
  through a real re-harden of the submitted CORDIC-1 design;
- the PMOS half + a possible re-run with k_P are the natural continuation when
  devphys stage-8 lands.

## Reproduce
```
python flow/v3/longL_gate.py            # longer-L refutation + stack check (BSIM)
python flow/v3/crosscheck_devices.py    # devphys(TCAD) vs BSIM on the own NMOS (+fig)
python flow/v3/xcheck_liberty.py        # -> out/own_devphys_xcheck.lib
python flow/v3/reharden_compare.py      # re-harden CORDIC-1: BSIM vs cross-checked
```
Local-only (devphys is a sibling repo; oss-cad-suite yosys for the re-harden).
No layout.py / make_dff.py edits — the Codex geom-check pin (commit 2718d05)
stays valid.
