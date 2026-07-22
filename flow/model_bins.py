#!/usr/bin/env python3
"""stdcells v3 — BSIM model-bin membership checker for sky130 1.8 V core FETs.

The operational form of the research finding "DRC-clean != model-valid": a
DRC-legal (W, L) can still fall in a GAP between the sparse BSIM bin rectangles,
where the compact model is uncharacterized and any ngspice number is
extrapolation. This tool answers, for a given (W, L, flavor): which bin does it
land in, or is it OFF-BIN?

Reads the PDK's binned `.pm3.spice` model files directly (the bin rectangles
`lmin/lmax/wmin/wmax` are corner-independent, so one corner file per flavor is
enough). Read-only; touches no repo.

    python model_bins.py <flavor> <W_um> <L_um>   # query one geometry
    python model_bins.py --summary                # bin envelope per flavor
    python model_bins.py --selftest               # sanity checks

flavors: nfet_01v8  pfet_01v8  nfet_01v8_lvt  pfet_01v8_hvt  pfet_01v8_mvt

Part of the v3 leg (see V3-PLAN.md, Phase 0). The "devphys zone" it computes
(W in [0.15, 0.36) um for nfet, where no BSIM bin exists) is the one regime
where a v3 device genuinely needs devphys TCAD rather than stock ngspice+BSIM.
"""
import re
import sys
from pathlib import Path

def _pdk():
    """PDK root — honour flow/common.py (single source of truth), else derive."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from common import PDK as _P
        return Path(_P)
    except Exception:
        return (Path.home() / ".ciel" / "ciel" / "sky130" / "versions" /
                "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A")


PDK = _pdk()
PR_SPICE = PDK / "libs.ref" / "sky130_fd_pr" / "spice"

FLAVORS = ["nfet_01v8", "pfet_01v8", "nfet_01v8_lvt",
           "pfet_01v8_hvt", "pfet_01v8_mvt"]

_BIN_RE = re.compile(
    r"lmin\s*=\s*(\S+)\s+lmax\s*=\s*(\S+)\s+wmin\s*=\s*(\S+)\s+wmax\s*=\s*(\S+)")


def _model_file(flavor):
    """One binned model file for `flavor` (any corner — bins are the same)."""
    hits = sorted(PR_SPICE.glob(f"sky130_fd_pr__{flavor}__*.pm3.spice"))
    if not hits:
        raise FileNotFoundError(
            f"no .pm3.spice for {flavor} under {PR_SPICE}")
    return hits[0]


def bins(flavor):
    """List of bin rectangles for `flavor`, each (lmin, lmax, wmin, wmax) in um."""
    text = _model_file(flavor).read_text()
    out = []
    for m in _BIN_RE.finditer(text):
        lmin, lmax, wmin, wmax = (float(x) * 1e6 for x in m.groups())  # m -> um
        out.append((lmin, lmax, wmin, wmax))
    if not out:
        raise ValueError(f"parsed 0 bins for {flavor} — format changed?")
    return out


def find_bins(flavor, w_um, l_um):
    """Bins whose rectangle contains (l_um, w_um), inclusive on both edges."""
    return [b for b in bins(flavor)
            if b[0] <= l_um <= b[1] and b[2] <= w_um <= b[3]]


def envelope(flavor):
    bs = bins(flavor)
    return {
        "n": len(bs),
        "L": (min(b[0] for b in bs), max(b[1] for b in bs)),
        "W": (min(b[2] for b in bs), max(b[3] for b in bs)),
        "L_edges": sorted({round(b[0], 4) for b in bs} |
                          {round(b[1], 4) for b in bs}),
        "W_edges": sorted({round(b[2], 4) for b in bs} |
                          {round(b[3], 4) for b in bs}),
    }


# The hand-added sub-min devices. MEASURED 2026-07-22: they do NOT extend the
# model floor below the continuous model — special_nfet_01v8 is 2 bins at
# W[0.36,0.42]/L[0.15,0.18], overlapping the continuous low corner. So the union
# of all installed BSIM models still floors at W ~ 0.36 um.
SPECIAL = {"nfet_01v8": "special_nfet_01v8",
           "pfet_01v8_hvt": "special_pfet_01v8_hvt"}
DRC_WIDTH_FLOOR = 0.15   # difftap.1 (0.14 inside areaid.ce)


def special_env(flavor):
    """(#bins, Wmin, Wmax, Lmin, Lmax) um for the flavor's special_ device, else None."""
    dev = SPECIAL.get(flavor)
    if not dev:
        return None
    hits = sorted(PR_SPICE.glob(f"sky130_fd_pr__{dev}*.pm3.spice"))
    if not hits:
        return None
    bs = [[float(x) * 1e6 for x in m.groups()]
          for m in _BIN_RE.finditer(hits[0].read_text())]
    if not bs:
        return None
    return (len(bs), min(b[2] for b in bs), max(b[3] for b in bs),
            min(b[0] for b in bs), max(b[1] for b in bs))


# --------------------------------------------------------------------------

def query(flavor, w_um, l_um):
    if flavor not in FLAVORS:
        sys.exit(f"unknown flavor {flavor!r}; choose from {FLAVORS}")
    hit = find_bins(flavor, w_um, l_um)
    print(f"{flavor}  W={w_um} um  L={l_um} um")
    if hit:
        for b in hit:
            print(f"  IN-BIN  L[{b[0]:.4g}, {b[1]:.4g}] x "
                  f"W[{b[2]:.4g}, {b[3]:.4g}] um")
        print("  -> model-valid (a real BSIM bin covers this geometry)")
        return 0
    env = envelope(flavor)
    print(f"  OFF-BIN — no bin rectangle covers (L={l_um}, W={w_um}).")
    print(f"     flavor envelope: L {env['L'][0]:.4g}..{env['L'][1]:.4g} um, "
          f"W {env['W'][0]:.4g}..{env['W'][1]:.4g} um, {env['n']} bins")
    print("  -> compact model UNCHARACTERIZED here; ngspice would extrapolate.")
    return 2


def summary():
    for fl in FLAVORS:
        try:
            e = envelope(fl)
        except FileNotFoundError as ex:
            print(f"{fl:16s} (missing: {ex})")
            continue
        print(f"{fl:16s} {e['n']:>4} bins   "
              f"L {e['L'][0]:.3g}..{e['L'][1]:.4g} um   "
              f"W {e['W'][0]:.3g}..{e['W'][1]:.4g} um")
        print(f"{'':16s}   L edges (um): "
              f"{', '.join(f'{x:g}' for x in e['L_edges'])}")
        print(f"{'':16s}   W edges (um): "
              f"{', '.join(f'{x:g}' for x in e['W_edges'][:16])}"
              f"{' ...' if len(e['W_edges']) > 16 else ''}")
    print()
    print(f"DRC width floor = {DRC_WIDTH_FLOOR} um (0.14 inside areaid.ce). "
          "Where BSIM stops = the 'devphys zone':")
    for fl in FLAVORS:
        try:
            wfloor = envelope(fl)["W"][0]
        except FileNotFoundError:
            continue
        sp = special_env(fl)
        spn = (f"special_ adds only W[{sp[1]:.3g},{sp[2]:.3g}]@L[{sp[3]:.3g},"
               f"{sp[4]:.3g}] -- does NOT lower the floor" if sp
               else "no special_ device")
        print(f"  {fl:16s} BSIM W floor {wfloor:.3g} um; {spn}")
        if wfloor > DRC_WIDTH_FLOOR:
            print(f"{'':18s}-> devphys zone (DRC-legal, uncharacterized): "
                  f"W in [{DRC_WIDTH_FLOOR}, {wfloor:.3g}) um")


def coverage(flavor):
    """Do the bins TILE their edge-grid envelope, or are there interior gaps?

    The bins align to a set of L/W edges; test each edge-grid cell's centre.
    An uncovered centre = an interior gap (a DRC-legal, in-envelope geometry
    with no compact model). Empirically (2026-07-22) all four core flavors
    tile with ZERO gaps, so off-bin only ever means OUTSIDE the envelope.
    """
    bs = bins(flavor)
    Le = sorted({b[0] for b in bs} | {b[1] for b in bs})
    We = sorted({b[2] for b in bs} | {b[3] for b in bs})
    cells = gaps = 0
    examples = []
    for i in range(len(Le) - 1):
        for j in range(len(We) - 1):
            cells += 1
            if not find_bins(flavor, 0.5 * (We[j] + We[j + 1]),
                             0.5 * (Le[i] + Le[i + 1])):
                gaps += 1
                if len(examples) < 5:
                    examples.append((Le[i], Le[i + 1], We[j], We[j + 1]))
    return {"bins": len(bs), "cells": cells, "gaps": gaps, "examples": examples}


def coverage_report():
    for fl in FLAVORS:
        try:
            c = coverage(fl)
        except FileNotFoundError:
            print(f"{fl:16s} (no model file)")
            continue
        tile = "TILES (no interior gaps)" if c["gaps"] == 0 \
            else f"{c['gaps']} INTERIOR GAPS"
        print(f"{fl:16s} {c['bins']:>4} bins / {c['cells']:>4} cells -> {tile}")
        for g in c["examples"]:
            print(f"     gap L[{g[0]*1:.3g}, {g[1]:.3g}] x W[{g[2]:.3g}, {g[3]:.3g}] um")


def selftest():
    checks = [
        # (flavor, W, L, expect_in_bin, note)
        ("nfet_01v8", 0.42, 0.15, True, "std minimum-width logic NFET"),
        ("nfet_01v8", 0.65, 0.15, True, "typical logic NFET"),
        ("pfet_01v8", 1.0, 0.15, True, "typical logic PFET"),
        ("nfet_01v8", 0.55, 4.73, True,
         "issue #228 decap12 — actually IN-BIN in the installed bins "
         "(refines the research's 1-2 per-cell claim)"),
        ("nfet_01v8", 0.38, 0.16, True,
         "W in [0.36,0.42): still INSIDE the continuous model"),
        ("nfet_01v8", 0.25, 0.15, False,
         "DRC-legal but W<0.36 -> the devphys zone (no BSIM bin, incl special_)"),
        ("nfet_01v8", 0.30, 3.0, False, "W<0.36 um: below the model-W envelope"),
        ("nfet_01v8", 0.65, 200.0, False, "L>100 um: above the model-L envelope"),
        ("nfet_01v8", 0.05, 0.15, False, "sub-DRC width, far below any bin"),
    ]
    ok = True
    for fl, w, l, exp, note in checks:
        got = bool(find_bins(fl, w, l))
        flag = "ok " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print(f"  [{flag}] {fl} W={w} L={l}: in_bin={got} (expect {exp})  {note}")
    # the tiling property the off-bin semantics rely on
    tiled = all(coverage(fl)["gaps"] == 0 for fl in
                ["nfet_01v8", "pfet_01v8", "nfet_01v8_lvt", "pfet_01v8_hvt"])
    print(f"  [{'ok ' if tiled else 'FAIL'}] all core flavors tile their "
          f"envelope (0 interior gaps): {tiled}")
    ok = ok and tiled
    print("SELFTEST", "PASS" if ok else "FAILED")
    return 0 if ok else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--summary":
        summary()
        return 0
    if argv[0] == "--coverage":
        coverage_report()
        return 0
    if argv[0] == "--selftest":
        return selftest()
    if len(argv) != 3:
        sys.exit("usage: model_bins.py <flavor> <W_um> <L_um> | --summary | "
                 "--selftest")
    return query(argv[0], float(argv[1]), float(argv[2]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
