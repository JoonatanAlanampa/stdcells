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
