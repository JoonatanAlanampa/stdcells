# Off-bin rectangular nfet gate-check — RESULT (2026-07-23)

**VERDICT: the pinned v3 "devphys where BSIM stops" proof device — a rectangular
W ≈ 0.25 µm NMOS — is a DEAD-END, the same class as the annular device. It is
DRC-forbidden by magic `diff/tap.2` (transistor width < 0.42 µm), and BSIM
refuses to model it. The BSIM model floor and the magic transistor-width floor
COINCIDE, so there is NO manufacturable-but-unmodeled rectangular transistor.
This closes the LAST of the three "own device where BSIM stops" targets.**

This was the surviving v3 target after narrow-width (no silicon effect) and
annular (`poly.11` "no bends in transistors") both closed. It closes too — and
for the same structural reason all three did: **the foundry models exactly what
it lets you build**, so "where BSIM stops" is always "where you cannot build".

---

## The experiment

`draw_offbin.py` draws two standalone dogbone NMOS test devices (narrow diff
strip = channel width under the gate; flares to 0.42 µm S/D contact pads):

| device | W (channel) | L | KLayout `sky130A_mr.drc` | `model_bins.py` |
|---|---|---|---|---|
| `nfet_w250` | **0.25 µm** | 0.15 µm | **CLEAN** (`run_offbin_drc.py`) | **OFF-BIN** |
| `nfet_w420` | 0.42 µm | 0.15 µm | CLEAN | IN-BIN |

Both pass the KLayout **manufacturing** deck clean — it has *no* transistor-width
rule (only `difftap.1`, the 0.15 µm plain-diff *shape* floor). The magic CI
(`offbin.yml`, mirrors `annular.yml`) then runs magic DRC + extract + netgen LVS.

## What magic said (CI run 29991101835 / 29991663438)

- **magic EXTRACTS both correctly** — the tools are fine, exactly as for annular:
  - `nfet_w250`: `X0 D G S VSUBS sky130_fd_pr__nfet_01v8 … w=0.25 l=0.15`
  - `nfet_w420`: `X0 D G S VSUBS sky130_fd_pr__nfet_01v8 … w=0.42 l=0.15`
  Correct device type, all four terminals, exact drawn W and L.
  **netgen LVS: "Circuits match uniquely" for both** — the extracted device is
  confirmed identical to the intended `nfet_01v8` at the drawn W/L. The tools
  handle the geometry; the *rules* are what forbid it.
- **but magic DRC FORBIDS the W=0.25 device** — `diff/tap.2`
  **"Transistor width < 0.42 µm"** fires (10 violations total incl. it), while
  `nfet_w420` shows **no** `diff/tap.2` (8 incidental standalone tap/latch-up
  rules only, same as the annular controls). The rule (magic `sky130A.tech`):

  ```
  edge4way *poly allfetsstd     420  "Transistor width < 0.42 (diff/tap.2)"
  edge4way *poly allfetsspecial 360  "Transistor in standard cell width < 0.36"
  # Except: standard cells allow transistor width minimum 0.36um
  ```
- **KLayout passed BOTH** (0 violations) — confirming, again, **KLayout-clean ≠
  rule-clean**; magic (the foundry deck) is the real gate.

## The three coinciding walls at (W=0.25 µm, L=0.15 µm)

1. **magic `diff/tap.2`** forbids *building* it (< 0.42 µm std / 0.36 µm special).
   [this gate-check, CI]
2. **BSIM refuses to model it** — `ngspice` on `sky130_fd_pr__nfet_01v8` at
   (W=0.25, L=0.15) errors **"could not find a valid modelname"** (no bin exists;
   the lowest L=0.15 bin is W=0.39). Not extrapolation — outright refusal.
   [`devphys_offbin.py`, local]
3. **No narrow-width silicon effect** to model in the first place.
   [devphys Phase-0, `devphys/07_nfet_3d`]

They coincide because they are the same boundary. `model_bins.py --summary`
(corrected this session) proves it for all four core flavors: the BSIM W-floor
equals the magic FET floor (0.36 µm where a `special_` device exists, else
0.42 µm) → **"unmodeled-but-legal FET: NONE (floors coincide)"** for every flavor.

## Tooling bug this exposed and fixed

`model_bins.py` had computed a **"devphys zone" of W ∈ [0.15, 0.36)** — DRC-legal
but unmodeled — using `difftap.1` (0.15 µm) as the DRC floor. That is the wrong
rule: `difftap.1` is the min width of a plain diffusion *shape*; a **gated
transistor** is floored by `diff/tap.2` at 0.42 µm (0.36 special). Corrected:
the transistor floor ≈ the BSIM floor, the "devphys zone" is **empty**. The
research note (`custom-devices.md`) conflated the two rules under the shared
name `diff/tap.2` (in KLayout `difftap.2` is the *relaxed 0.14 µm* in-core diff
width; in magic `diff/tap.2` is the *0.42 µm transistor* rule — different rules,
same number).

## devphys characterization — done, and honestly reframed

`devphys_offbin.py` did characterize the off-bin device "where BSIM can't":
because the devphys stage-4c nfet is 2D (current is per-unit-width × W,
`mosfet_short.py:280`), it emits an I-V at **any** W. So devphys gives the
W=0.25 device Ion ≈ 120 µA (silicon-calibrated per-µm × 0.25) where BSIM returns
nothing — **but that is pure width-scaling with no narrow-W physics** (wall 3),
for a device you cannot build (wall 1). devphys's *reach* here fills no real gap.

The **reframed, real value** (what the grand goal needs): devphys reproduces
BSIM from silicon-calibrated physics at **manufacturable** widths —

| W | BSIM ngspice Ion | devphys Ion | Δ |
|---|---|---|---|
| 0.42 µm (floor) | 185.4 µA | 201.7 µA | +8.8 % |
| 0.65 µm | 296.2 µA | 312.1 µA | +5.4 % |
| 1.00 µm | 476.9 µA | 480.2 µA | +0.7 % |

(the residual at narrow W is the ~1/W S/D-resistance the linear width-scaling
over-predicts; devphys stage 4d `mosfet_rsd.py` models it). See
`devphys_offbin.png`. This is the deliverable: an **independent from-physics
characterization of the cells you can actually build** — not a gap-filler for
geometries no one can manufacture.

## Consequence for v3

All three exotic "devphys where BSIM stops" targets are now closed
(narrow-width, annular, off-bin rectangular). The grand-goal "own-devices"
capability is what the reframe already found (annular RESULT.md): devphys's
silicon-calibrated physics chain (stages 4–5) as an **independent cross-check /
from-physics characterization of the OWN STANDARD (rectangular) cells** — not the
pursuit of geometries at or past the process rules. `V3-PLAN.md` updated.

## Reproduce
```
python flow/offbin/draw_offbin.py         # GDS + LVS refs
python flow/offbin/run_offbin_drc.py      # local KLayout DRC (both clean)
python flow/offbin/devphys_offbin.py      # devphys vs BSIM + figure (needs ../devphys)
# push flow/offbin/** -> offbin.yml runs magic DRC/extract + netgen LVS in CI
```
