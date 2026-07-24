# stdcells v3 — devphys-derived custom device geometries (DRAFT PLAN)

**Status:** v3 leg started 2026-07-22 (Opus session). Phase 0 (device-validity)
is done — see `flow/model_bins.py`. This is the next leg after lib-v1.0 (zero
foundry) / lib-v1.1 (multi-PVT) / lib-v1.2 (internal_power).
**Prereq read:** `../research/custom-devices.md` (esp. its 2026-07-22
RESOLUTIONS + the `model_bins.py` UPDATE).

## Thesis, and the real wall
v3's premise is NON-STANDARD geometry. DRC barely constrains that — L and W are
continuous on a 5 nm grid, "flavor" is just which implant layers you draw. The
wall is **MODEL VALIDITY**: off-standard geometry is exactly where sky130's BSIM
bins stop being characterized, so an `ngspice → Liberty` flow there is
extrapolation dressed as measurement. **devphys** (TCAD calibrated to measured
sky130 silicon, github/devphys) is the intended stand-in for BSIM where BSIM
runs out. So v3's foundation is a PROOF that devphys can characterize a custom
geometry BSIM can't — before any library leans on it.

## Scope (decision 2026-07-22)
- **(a) NON-STANDARD RECTANGULAR geometries** — custom L / W / stacking,
  devphys-tuned. Builds directly on lib-v1.0/v1.1 (already a hand-drawn
  non-PDK-standard library). **THIS IS THE v3 MAIN PATH.**
- **(b) EXOTIC structures (annular / ring-gate)** — the research flags these as
  an open risk (likely mis-extract, no defined W). **GATED SPIKE, not the main
  path:** one small annular device through magic-extract + netgen LVS + KLayout
  DRC FIRST; design nothing around it until that passes.

## Device envelope (Phase 0 findings so far — from the decks/models)
- **Min FET width = 0.15 µm** (0.14 inside `areaid.ce`), on the 5 nm grid.
  [both KLayout `difftap.1/.2` and magic `width … 150`]
- **Min L = 0.15 µm** core; **0.35 µm** for an lvtn PFET (`poly.1b`). Continuous
  `nfet_01v8` L-bin edges: 0.15 / 0.18 / 0.25 / 0.5 / 1 / 2 / 4 / 8 / 20 / 100 µm.
- **No hvt NMOS** → NMOS leakage control must be **GEOMETRIC** (longer L,
  stacking). PMOS has svt/lvt/hvt/mvt.
- **Model bins are SPARSE rectangles, not a full grid** → a DRC-legal (W,L) can
  miss every bin. `nfet_01v8` = 360 bins (W-edges fine 0.36–0.84 µm, coarse
  above); `special_nfet_01v8` covers the sub-0.42 regime.

## Tooling split (this Windows box)
- **LOCAL:** deck/model reads, gdstk drawing, KLayout DRC + LVS, ngspice, devphys.
- **CI / container (Linux):** magic DRC/extract, netgen LVS.
→ magic-side checks are CI jobs (reuse stdcells `magic.yml` + `run_lvs_all.py`).

## Phases
### Phase 0 — device-validity envelope + the model-bin gate  [mostly local]
- **0.1 DONE:** min width resolved (0.15/0.14 µm); L mins; flavor asymmetry;
  model-bin edges mapped for the 4 core flavors (see RESOLUTIONS).
- **0.2 BUILD `flow/model_bins.py`:** given (W, L, flavor) return the BSIM bin
  or flag OFF-BIN, by parsing the `.pm3.spice` bin rectangles. The operational
  form of "DRC-clean ≠ model-valid"; every v3 geometry passes through it before
  its characterization is trusted.
- **0.3 Confirm the drawn floor empirically:** an under-width (0.14/0.15 µm)
  test cell through KLayout (local) + magic DRC/extract (CI) — does it extract
  as `nfet_01v8` or need `special_`? Resolves research Q1's empirical half and
  Q4 (`areaid.sc` multi-finger fidelity) with a companion multi-finger cell.

### Phase 1 — close the devphys↔model loop on ONE device  [the go/no-go]
Pick a devphys-motivated geometry: a **longer-L NMOS for geometric leakage
control** (the natural play given there is no hvt NMOS). Draw it (gdstk); run
the full chain — KLayout + magic DRC, magic extract, LVS (both), model-bin
check — and characterize it TWICE: stock BSIM ngspice AND devphys TCAD.
**SUCCESS = devphys predicts the extracted device's I–V / leakage, especially
where it is off-bin or where geometric leakage control shows up.** This decides
whether v3 is real: if devphys and BSIM disagree *inside a valid bin*, devphys's
calibration is the suspect; if they agree in-bin and devphys extends cleanly
off-bin, v3 has its characterization path.

### Phase 2 — a small v3 library + re-harden
Build a handful of v3 cells (INV/NAND2/NOR2/DFF) on the validated custom devices
(e.g. geometric-"hvt" NMOS), characterize via the Phase-1 path, re-harden
CORDIC-1 (as v1/v2 did), compare PPA + leakage vs lib-v1.x. Gates: zero foundry
content (v3 is still own-cells), DRC/LVS/magic clean, model-valid geometries only.

## Still-open research questions needing experiments (Q2–Q4)
- **Q2** annular extract / LVS / W-definition — the (b) gated spike.
- **Q3** which rules the OPEN decks cannot verify (closed-doc-only) that bear on
  the custom envelope.
- **Q4** open-deck `areaid.sc` multi-finger fidelity — folded into Phase 0.3.

## Model / effort note
This leg is diagnosis-shaped (geometry rules, model validity, TCAD-vs-BSIM) =
the Fable / xhigh category (model-routing-policy). Fable budget exhausted until
Fri; running Opus xhigh as the substitute. The **Phase-1 devphys-vs-BSIM
adjudication** is the most Fable-worthy step — consider queueing it for Fable.

## REFINEMENT 2026-07-22 — model_bins.py reshapes devphys's role
`research/model_bins.py` (built this session; `--selftest` PASS, `--coverage`)
shows the core BSIM bins TILE their (L,W) envelope with **zero interior gaps**
for all four flavors — off-bin = outside the envelope only (W < 0.36/0.42 µm or
L > 100 µm). So for **scope (a)** rectangular geometries, stock ngspice+BSIM
already covers the whole useful design space (as it did for lib-v1.0/v1.1):
**devphys is a CROSS-CHECK there, not a necessity.** devphys's *unique*
characterization value concentrates where BSIM genuinely stops:
1. exotic structures (annular, scope b) — no BSIM model at all;
2. the sub-envelope narrow-width regime (W < 0.36/0.42 µm — only the thin
   `special_` device);
3. independent physics validation of BSIM's geometry extrapolation (in-bin ≠
   silicon-validated at that exact geometry — Finding 2 gives validity as bias
   envelopes only, never geometry).

**Phase 1 pick, revised.** A longer-L NMOS is IN-envelope (L ≤ 100 µm), so BSIM
handles it — keep it as the scope-(a) geometric-leakage lever, but it is NOT the
"devphys where BSIM stops" proof. For that proof, target a **sub-min-width
device** (W just below 0.36 µm, where the continuous model ends and only
`special_` exists) or the annular spike (b). Net: scope (a) is lower-risk than
the plan first implied (BSIM covers it); devphys's headline justification now
rests on (b) + the sub-envelope regime, which sharpens — and partly gates — how
much of v3 truly *needs* devphys vs. merely benefits from it.

**PHASE 1 DEVICE, PINNED (2026-07-22).** The `special_` devices do NOT extend
the floor below the continuous model, so the BSIM floor is W ≈ 0.36 µm (nfet) /
0.42 µm (pfet, lvt) and the devphys zone is W ∈ [0.15, 0.36) / [0.15, 0.42) µm.
The clean "devphys where BSIM stops" proof device = a **W ≈ 0.25 µm NMOS**
(L 0.15 µm): DRC-legal (> 0.15 floor) but inside the devphys zone where NO BSIM
bin — continuous *or* `special_` — exists (`model_bins.py nfet_01v8 0.25 0.15`
→ OFF-BIN). Flow: draw (gdstk) → KLayout DRC (local) + magic DRC/extract + LVS
(CI) → characterize by devphys TCAD (BSIM cannot, by construction) →
sanity-check the trend against the nearest in-bin device (W = 0.36). This is the
sharpest test of the v3 thesis: a geometry BSIM literally has no model for. Keep
the longer-L NMOS as the scope-(a) leakage lever (in-envelope, BSIM-characterized).

## PHASE 1 RESULT (2026-07-23) — off-bin target CLOSED; all three exotic targets closed
The gate-check ran (flow/offbin/, offbin.yml CI green, see offbin/RESULT.md).
**The pinned off-bin W=0.25 µm rectangular NMOS is a DEAD-END** — magic
`diff/tap.2` "Transistor width < 0.42 µm" (0.36 special_ in a std cell) FORBIDS
it (10 viol incl. it; W=0.42 control clean), and BSIM `ngspice` REFUSES it
("could not find a valid modelname"). Both decks' KLayout runs passed it —
KLayout has no transistor-width rule (only `difftap.1` = 0.15 µm plain-diff
*shape*). magic extracts + netgen-LVS-matches both as `nfet_01v8` at the drawn
W/L — the tools are fine, the RULES forbid it. Same class as annular (poly.11).
- **Root correction:** the Phase-0 "devphys zone W ∈ [0.15, 0.36)" was an
  ARTIFACT of using the plain-diff floor (0.15) as the transistor floor. The real
  gated-FET floor is magic `diff/tap.2` (0.42 std / 0.36 special_), which
  COINCIDES with the BSIM model floor — for ALL four core flavors
  (`model_bins.py --summary`, corrected). => **No manufacturable-but-unmodeled
  rectangular transistor exists**; the "sharpest test" device is un-buildable.
- **So all THREE "devphys where BSIM stops on a custom geometry" targets are
  CLOSED**: narrow-width (no silicon effect), annular (poly.11), off-bin
  rectangular (diff/tap.2 = BSIM floor). They close for the same structural
  reason: **the foundry characterizes exactly what it lets you build**, so "where
  BSIM stops" is always "where you cannot build."
- **REFRAME (v3's actual, deliverable value):** devphys's silicon-calibrated
  physics chain (stages 4–5) as an INDEPENDENT from-physics characterization /
  cross-check of the OWN STANDARD (rectangular, manufacturable) cells — NOT a
  gap-filler for exotic geometries. Demonstrated (devphys_offbin.py): devphys
  reproduces BSIM Ion at manufacturable widths within +0.7 % (W=1.0) … +8.8 %
  (W=0.42 floor; the residual is the ~1/W S/D-resistance the 2D scalar-W model
  over-predicts — devphys stage 4d models it). Scope (a) = the real v3 path;
  scope (b) exotic geometries = closed. Phase 2 (a small v3 library on validated
  custom RECTANGULAR devices, re-harden vs lib-v1.x) stands, on the cross-check
  footing — NOT on a "BSIM can't" necessity claim.

## PHASE 2 RESULT (2026-07-24) — delivered on the cross-check footing (flow/v3/RESULT.md)
Phase 2 executed as the reframe, NOT as an hvt cell set. Three parts:
- **The suggested vehicle is a 4th dead-end.** `flow/v3/longL_gate.py` (BSIM):
  a longer-L "geometric-hvt" NMOS gives NO leakage win on sky130 — DIBL falls
  with L but the halo/RSCE implants lower Vt by the same amount, so **Ioff is
  flat at 25 °C** (~1.9 pA) and Ion/Ioff only worsens; at 100 °C the best step
  is a marginal ×1.09. Longer-L joins narrow-width / annular / off-bin as the
  4th closed "geometric leakage control" target (same structural cause: the
  halo engineering flattens leakage vs geometry). The other named lever,
  STACKING, IS real (3.5× less Ioff @100 °C) but hot-corner-only and already
  used in NAND2/NOR2 → not a new-cell opportunity. Building longer-L cells would
  also need a full per-cell hand-redraw (shared N/P poly gate in layout.py) for
  a strictly-worse library.
- **The real deliverable — devphys cross-checks the OWN NMOS.**
  `flow/v3/crosscheck_devices.py`: devphys stages 4c/4d (TCAD, silicon-calibrated,
  L=0.15) vs BSIM on nfet_01v8 W=0.65 → **Ion agrees +4.7 %** (309 vs 295 µA)
  from fully independent physics. Honest gaps reported: linear +13 % (Rsd
  mobility roll-off), DIBL +46 % (2D halo proxy). **PMOS (pfet W=1.0) deferred**
  to the devphys session's in-flight stage-8 (pfet_short_results.npz absent);
  we do not run/edit devphys.
- **Cross-checked liberty + re-harden.** `flow/v3/xcheck_liberty.py` scales the
  fall (NMOS) arcs of own.lib by 1/k_N=0.955 → `out/own_devphys_xcheck.lib`
  (a first-order device-drive sensitivity view, rise/PMOS left on BSIM).
  `flow/v3/reharden_compare.py`: CORDIC-1 synthesizes to an **IDENTICAL** gate
  netlist / cells (1805) / area (9913 µm²) under both → same silicon shape; the
  only PPA delta is the −4.5 % fall-path timing band. **own physics → own cells
  → silicon, cross-checked.**
- NOT touched: layout.py / make_dff.py (Codex geom-pin @2718d05 stays valid).
- Continuation when devphys stage-8 lands: add the PMOS half (k_P), optionally
  re-run the cross-checked liberty with both device ratios.
