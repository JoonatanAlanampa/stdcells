# Annular nfet gate-check — RESULT (2026-07-22)

**VERDICT: annular / ring-gate devices are a DRC DEAD-END on sky130. Not viable
for the v3 library.**

magic-extract CI (`annular.yml`, run 29930431195) on the annular nfet that is
DRC-clean under the KLayout manufacturing deck:

- **magic EXTRACTS it as a valid nfet** —
  `X0 D G S VSUBS sky130_fd_pr__nfet_01v8 ad=0.1024 pd=1.28 as=1.4664 ps=8.3 w=1.75 l=0.15`.
  Drain/gate/source/substrate all correct; L = 0.15 µm exact; **W = 1.75 µm**, a
  defined finite value (~ the mean gate perimeter). This **refutes** the
  research's fear (custom-devices.md §3/Q2) that a ring gate "mis-extracts / has
  no defined W". The tools handle it fine.
- **but magic DRC FORBIDS it — 30 violations, headed by**
  `poly.11: No bends in transistors`. sky130's process rules **explicitly
  prohibit a bent/closed-loop transistor gate.** (Also: `diff/tap.2` Transistor
  width < 0.42 µm; `poly.7` diff overhang; `poly.8` poly overhang; `poly.4`
  poly–diff spacing; `licon.8/8a/14` poly-contact rules.)
- **the KLayout manufacturing deck passed the same layout with 0 violations** —
  CONFIRMS the research point that KLayout is more permissive; magic (and the
  foundry) is the real gate. KLayout-clean != rule-clean.

## Consequence

Annular is closed — not because the tools can't handle it (they extract a
sensible W), but because the process design rules disallow the geometry.

Combined with the **narrow-width Phase-0 result** (`../../../devphys/07_nfet_3d/`,
no clean narrow-width effect in measured silicon), **both** "devphys where BSIM
stops on a custom geometry" targets are now closed:
- narrow width: no effect to model;
- annular: forbidden by `poly.11`.

So the grand-goal "own-devices" capability should **reframe** to what is actually
reachable and valuable: devphys's physics-grounded, silicon-calibrated model
chain (stages 4–5) applied to the **own standard (rectangular) cells** — an
independent from-physics characterization path for the stdcells library — rather
than chasing exotic geometries at the edge of, or outside, the process rules.
See `../../V3-PLAN.md` and `../../../research/stdcells-v3-plan.md` REFINEMENT.
