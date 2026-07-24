"""v3 Phase 2: emit the devphys-cross-checked liberty from the BSIM own.lib.

This is a FIRST-ORDER device-drive cross-check, not a re-characterization, and
is labelled as such. The device cross-check (crosscheck_devices.py) found the
library's pull-down NMOS (nfet_01v8 W=0.65 L=0.15) drives Ion = 309 uA from
devphys's independent silicon-calibrated physics vs 295 uA from BSIM: k_N =
1.047. To first order a cell's propagation delay is drive-limited (t ~ C*Vdd/I),
so the pull-down (cell_fall / fall_transition) arcs scale by 1/k_N = 0.955 when
the drive follows devphys instead of BSIM.

We therefore take the signed-off BSIM own.lib and scale ONLY the cell_fall and
fall_transition tables by 1/k_N, leaving:
  * cell_rise / rise_transition  -- PULL-UP (PMOS) driven; the L=0.15 PMOS
    devphys solve is the devphys session's in-flight stage-8 work, so these stay
    on BSIM and are flagged. When pfet_short_results.npz lands, re-run with k_P.
  * internal_power, leakage, caps, areas, setup/hold -- unchanged (the
    cross-check is on drive strength / delay only).

What this is NOT: it is not a claim that devphys delays are "more correct" than
BSIM. The value is the CONVERGENCE -- two fully independent characterizations of
the same manufacturable device agree on drive to +4.7 %, so a library (and the
CORDIC-1 it hardens) built on the BSIM numbers rests on a foundation an
independent from-physics model reproduces. The scaled liberty makes that
agreement band explicit in the timing view; reharden_compare.py then shows the
gate netlist / cells / area are IDENTICAL and only the fall-path timing moves,
by the band.

Approximation stated plainly: delay is treated as purely drive-limited (ignores
the slew-shape and input-capacitance BSIM bakes into the NLDM, which devphys
does not re-derive). Good to first order at the ~5 % agreement level; it is a
sensitivity view, not a signoff library.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import OUT                                            # noqa: E402

RATIOS = HERE / "xcheck_ratios.json"

# blocks whose value tables scale with pull-down (NMOS) drive
_FALL_BLOCK = re.compile(r"^(cell_fall|fall_transition)\s*\(")
_QUOTED = re.compile(r'"([^"]*)"')


def _scale_row(inner, factor):
    """Scale a comma-separated numeric row string by factor, keep %.5f format."""
    try:
        nums = [float(x) for x in inner.split(",")]
    except ValueError:
        return inner                       # not a numeric row -- leave as-is
    return ", ".join(f"{x*factor:.5f}" for x in nums)


def scale_fall_arcs(text, factor):
    """Return `text` with every cell_fall/fall_transition value table scaled.

    State machine on brace depth: inside a cell_fall/fall_transition block, scale
    quoted numeric rows but never index_1/index_2 (the axis grids).
    """
    out, scaling, scale_depth, depth = [], False, None, 0
    for line in text.splitlines():
        stripped = line.strip()
        starts = bool(_FALL_BLOCK.match(stripped))
        if starts and not scaling:
            scaling, scale_depth = True, depth
        is_axis = stripped.startswith("index_1(") or stripped.startswith("index_2(")
        if scaling and not starts and not is_axis and '"' in line:
            line = _QUOTED.sub(lambda m: '"' + _scale_row(m.group(1), factor) + '"',
                               line)
        out.append(line)
        depth += line.count("{") - line.count("}")
        if scaling and depth <= scale_depth:
            scaling, scale_depth = False, None
    return "\n".join(out) + "\n"


# --- the physical cells + abc-lib derivation, mirrored from make_hardening.py so
# a real harden with the cross-checked lib is a drop-in (same recipe, scaled lib).
PHYS_CELLS = """
  cell (TIE_X1) { area : 3.7536; cell_leakage_power : 0.001;
    pin (HI) { direction : output; function : "1";
      max_capacitance : 0.100; }
    pin (LO) { direction : output; function : "0";
      max_capacitance : 0.100; } }
  cell (WELLTAP_X1) { area : 1.2512; cell_leakage_power : 0; }
  cell (DIODE_X1) { area : 2.5024; cell_leakage_power : 0;
    pin (DIODE) { direction : input; capacitance : 0.001; } }
  cell (FILL_X1) { area : 1.2512; cell_leakage_power : 0; }
  cell (FILL_X2) { area : 2.5024; cell_leakage_power : 0; }
  cell (FILL_X4) { area : 5.0048; cell_leakage_power : 0; }
  cell (FILL_X8) { area : 10.0096; cell_leakage_power : 0; }
"""


def add_phys_cells(text):
    full = text.rstrip()
    assert full.endswith("}"), "unexpected liberty tail"
    return full[:-1] + PHYS_CELLS + "}\n"


def main():
    if not RATIOS.exists():
        sys.exit("run crosscheck_devices.py first (xcheck_ratios.json missing)")
    k_n = json.loads(RATIOS.read_text())["k_nmos_ion"]
    factor = 1.0 / k_n
    src = (OUT / "own.lib").read_text()

    scaled = scale_fall_arcs(src, factor)
    # relabel the library so downstream tools don't confuse it with signoff own.lib
    scaled = scaled.replace("library (own_sky130_tt_025C_1v80)",
                            "library (own_devphys_xcheck_tt_025C_1v80)", 1)
    (OUT / "own_devphys_xcheck.lib").write_text(scaled)

    # comb-only (DFF stripped) for abc, + hardening (phys cells) — same as
    # make_hardening builds from own.lib, so a CI harden can point straight here.
    comb, n = re.subn(r"\n  cell \(DFF_X1\).*?\n  \}(?=\n)", "", scaled, flags=re.S)
    assert n == 1, "DFF_X1 block not found in scaled lib"
    (OUT / "own_devphys_xcheck_abc.lib").write_text(comb)
    (OUT / "own_devphys_xcheck_hardening.lib").write_text(add_phys_cells(scaled))

    # report how much moved
    n_fall = sum(1 for _ in re.finditer(r"(cell_fall|fall_transition)\s*\(", scaled))
    print(f"k_N (devphys/BSIM NMOS Ion) = {k_n:.4f}  ->  fall arcs x {factor:.4f} "
          f"({100*(factor-1):+.1f} %)")
    print(f"scaled {n_fall} cell_fall/fall_transition tables; rise/PMOS arcs on "
          "BSIM (devphys stage-8 pending)")
    print(f"wrote {OUT/'own_devphys_xcheck.lib'}")
    print(f"      {OUT/'own_devphys_xcheck_abc.lib'} (comb-only, for abc)")
    print(f"      {OUT/'own_devphys_xcheck_hardening.lib'} (+phys cells, for P&R)")
    print("STAGE: cross-checked liberty emitted")


if __name__ == "__main__":
    main()
