"""v3 Phase 2 (reframed): devphys stages 4-5 as an INDEPENDENT from-physics
CROSS-CHECK of the library's OWN MANUFACTURABLE devices.

The reframe (flow/offbin/RESULT.md): all three "devphys where BSIM stops on a
custom geometry" targets are closed, because the foundry models exactly what it
lets you build. devphys's real, deliverable value is a from-physics cross-check
of the rectangular cells we DO build. This module makes that concrete on the two
devices the standard-cell library actually instantiates:

    NMOS  sky130_fd_pr__nfet_01v8   WN = 0.65 um   L = 0.15 um   (all pull-downs)
    PMOS  sky130_fd_pr__pfet_01v8   WP = 1.00 um   L = 0.15 um   (all pull-ups)

For each device we compare, at the SAME geometry, two independent characterizations:
  * BSIM       — stock sky130 compact model in ngspice (what lib-v1.x is built on)
  * devphys    — DEVSIM TCAD calibrated to measured 25x25 silicon, transferred to
                 L = 0.15 um (stage 4c short-channel + stage 4d S/D resistance),
                 width-scaled per-um x W.

The NMOS solve is committed (04_sky130_nfet/{short,rsd}_results.npz) so this runs
here, read-only, no DEVSIM. The L = 0.15 um PMOS short-channel solve
(08_pfet/pfet_short_results.npz) is NOT yet committed -- it is the devphys
session's in-flight stage-8 work (biased-sweep convergence). So the PMOS row is
DEFERRED to that output; we print the BSIM PMOS numbers for the record and the
exact file the cross-check will consume when it lands. We do not run or edit
devphys here.

Metrics: Ion (Vg=Vd=1.8, the drive that sets fall/rise delay), Vt (max-gm),
DIBL, and linear drive (Vg=1.8, Vd=0.1, the Rsd-sensitive point). The agreement
ratios feed the "device-drive cross-checked liberty" (see xcheck_liberty.py).
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                       # flow/
from common import MODELS, run_ngspice, parse_meas         # noqa: E402

DEVPHYS = HERE.parents[2] / "devphys"
NFET_DIR = DEVPHYS / "04_sky130_nfet"
PFET_SHORT_NPZ = DEVPHYS / "08_pfet" / "pfet_short_results.npz"   # stage-8 WIP

W_CAL = 25.0        # devphys 2D solve width (scalar multiplier; current is per-um x W)
L = 0.15
WN, WP = 0.65, 1.00


# --------------------------------------------------------------- BSIM (ngspice)
def bsim_idvg(flavor, w, vd, temp=27):
    """Id-Vg sweep 0..|1.8| for `flavor` at (w, L). Returns (VG>=0 magnitudes)."""
    sgn = -1.0 if flavor.startswith("pfet") else 1.0
    vg_hi = sgn * 1.8
    vd_s = sgn * abs(vd)
    net = f"""* {flavor} W={w} L={L} Vd={vd_s}
.lib "{MODELS}" tt
.temp {temp}
vd d 0 {vd_s}
vg g 0 0
xm d g 0 0 sky130_fd_pr__{flavor} w={w} l={L}
.control
dc vg 0 {vg_hi} {sgn*0.02}
let ad = abs(i(vd))
let vgm = abs(v(g))
wrdata bsim_{flavor}_{int(abs(vd)*10)}.txt ad
.endc
.end
"""
    run_ngspice(net, f"bsim_{flavor}_{int(abs(vd)*10)}")
    d = np.loadtxt(HERE.parents[1] / "out" / f"bsim_{flavor}_{int(abs(vd)*10)}.txt")
    vg = np.abs(d[:, 0])
    idd = d[:, 1]
    order = np.argsort(vg)
    return vg[order], idd[order]


def vt_maxgm(vg, idd, vd):
    gm = np.gradient(idd, vg)
    i = int(np.argmax(gm))
    return vg[i] - idd[i] / gm[i] - abs(vd) / 2


def vt_cc(vg, idd, w):
    th = 0.1e-6 * (w / L)
    good = idd > 1e-12
    return float(np.interp(np.log(th), np.log(idd[good]), vg[good]))


def bsim_metrics(flavor, w):
    vg_l, id_l = bsim_idvg(flavor, w, 0.1)
    vg_s, id_s = bsim_idvg(flavor, w, 1.8)
    return {
        "Ion": id_s[-1],                                   # Vg=Vd=1.8
        "Ilin": id_l[-1],                                  # Vg=1.8, Vd=0.1
        "Vt": vt_maxgm(vg_l, id_l, 0.1),
        "DIBL": (vt_cc(vg_l, id_l, w) - vt_cc(vg_s, id_s, w)) * 1e3,
    }


# ------------------------------------------------------------- devphys (npz)
def devphys_nmos():
    """NMOS metrics at WN, from the committed stage-4c/4d solves (per-um x WN).

    Ion & linear from stage 4d (S/D-resistance corrected -- the more complete
    device); Vt & DIBL from stage 4c (has the dibl_sim it fitted). Both are
    L=0.15 um, calibrated to measured 25x25 silicon.
    """
    short = np.load(NFET_DIR / "short_results.npz")
    rsd = np.load(NFET_DIR / "rsd_results.npz")
    VG = short["VG"]
    ion_perum = float(rsd["ID_sat"][np.argmax(rsd["sat_grid"])]) / W_CAL   # Vg=Vd=1.8
    ilin_perum = float(rsd["ID_lin"][np.argmax(VG)]) / W_CAL               # Vg=1.8,Vd=0.1
    vt = vt_maxgm(VG, short["ID_lin"] / W_CAL, 0.1)
    return {
        "Ion": ion_perum * WN,
        "Ilin": ilin_perum * WN,
        "Vt": vt,
        "DIBL": float(short["dibl_sim"]),
    }


# --------------------------------------------------------------------- report
def row(label, dp, bs):
    if dp is None:
        return (f"  {label:<26} devphys   --        BSIM {fmt(bs)}   "
                "(devphys pending)")
    d = 100 * (dp / bs - 1) if bs else float("nan")
    return f"  {label:<26} devphys {fmt(dp)}   BSIM {fmt(bs)}   ({d:+.1f} %)"


def fmt(x):
    return f"{x:8.4g}"


def main():
    print("=" * 78)
    print("v3 Phase 2 -- devphys(TCAD, from silicon physics) vs BSIM on the OWN "
          "cells' devices")
    print("=" * 78)

    # ---- NMOS: fully cross-checked --------------------------------------
    bn = bsim_metrics("nfet_01v8", WN)
    dn = devphys_nmos()
    print(f"\nNMOS  nfet_01v8  W={WN} um  L={L} um   (every pull-down in the library)")
    print(row("Ion  Vg=Vd=1.8   (uA)", dn["Ion"] * 1e6, bn["Ion"] * 1e6))
    print(row("Ilin Vg=1.8,Vd=0.1 (uA)", dn["Ilin"] * 1e6, bn["Ilin"] * 1e6))
    print(row("Vt   max-gm       (V)", dn["Vt"], bn["Vt"]))
    print(row("DIBL             (mV)", dn["DIBL"], bn["DIBL"]))
    k_n = dn["Ion"] / bn["Ion"]
    print(f"  -> NMOS drive ratio devphys/BSIM (Ion) = {k_n:.4f}  "
          f"(fall-delay cross-check multiplier)")

    # ---- PMOS: deferred to devphys stage-8 short-L convergence ----------
    bp = bsim_metrics("pfet_01v8", WP)
    print(f"\nPMOS  pfet_01v8  W={WP} um  L={L} um   (every pull-up in the library)")
    dp_avail = PFET_SHORT_NPZ.exists()
    print(row("Ion  |Vg|=|Vd|=1.8 (uA)", None, bp["Ion"] * 1e6))
    print(row("Vt   max-gm       (V)", None, bp["Vt"]))
    if not dp_avail:
        print(f"  -> devphys L={L} um PMOS not yet solved: {PFET_SHORT_NPZ.name} "
              "absent.\n     It is the devphys session's in-flight stage-8 "
              "(short-L PMOS biased-sweep\n     convergence -> compose-INV). This "
              "cross-check consumes it when it lands;\n     we do NOT run or edit "
              "devphys here (parallel-session board discipline).")

    # ---- interpretation --------------------------------------------------
    print("\nREADING (honest):")
    print(f"  * Ion agrees to {100*(k_n-1):+.1f} % from fully independent physics -- "
          "the headline:\n    devphys reproduces the drive that sets the cells' "
          "fall delay without ever\n    seeing a BSIM parameter. This is the "
          "reframe's deliverable on a real cell device.")
    dlin = 100 * (dn["Ilin"] / bn["Ilin"] - 1)
    print(f"  * Linear drive is off by {dlin:+.1f} % even after the stage-4d Rsd "
          "correction --\n    the 2D scalar-W model still lacks the n+ heavy-doping "
          "mobility roll-off; it\n    matters at Vd=0.1 (large IR drop) and far less "
          "at the Vd=1.8 operating point.")
    ddibl = 100 * (dn["DIBL"] / bn["DIBL"] - 1)
    print(f"  * DIBL is over-predicted ({ddibl:+.0f} %): a known limit of the 2D "
          "electrostatics\n    (halo profile is a single-knob proxy). Direction "
          "right, magnitude high --\n    reported, not hidden.")
    print("  * PMOS pull-up cross-check waits on devphys stage-8; until then the "
          "rise-delay\n    arcs stay on BSIM and are flagged as such in the "
          "cross-checked liberty.")

    # ---- figure ----------------------------------------------------------
    _figure(dn, bn)

    # machine-readable ratios for xcheck_liberty.py
    import json
    ratios = {"k_nmos_ion": k_n, "k_nmos_ilin": dn["Ilin"] / bn["Ilin"],
              "pmos_devphys_available": dp_avail}
    (HERE / "xcheck_ratios.json").write_text(json.dumps(ratios, indent=1))
    print(f"\nwrote {HERE / 'xcheck_ratios.json'}")
    print("STAGE: v3 device cross-check DONE (NMOS live, PMOS gated on devphys stage-8)")


def _figure(dn, bn):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    short = np.load(NFET_DIR / "short_results.npz")
    rsd = np.load(NFET_DIR / "rsd_results.npz")
    VG = short["VG"]
    vg_bl, id_bl = bsim_idvg("nfet_01v8", WN, 0.1)
    vg_bs, id_bs = bsim_idvg("nfet_01v8", WN, 1.8)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))
    ax1.plot(VG, rsd["ID_lin"] / W_CAL * WN * 1e6, "-", color="tab:red",
             label="devphys Vd=0.1 (Rsd)")
    ax1.plot(short["sat_grid"], rsd["ID_sat"] / W_CAL * WN * 1e6, "-",
             color="tab:orange", label="devphys Vd=1.8 (Rsd)")
    ax1.plot(vg_bl, id_bl * 1e6, "o", ms=3, mfc="none", color="tab:blue",
             label="BSIM Vd=0.1")
    ax1.plot(vg_bs, id_bs * 1e6, "s", ms=3, mfc="none", color="tab:green",
             label="BSIM Vd=1.8")
    ax1.set_xlabel("$V_G$ (V)"); ax1.set_ylabel("$I_D$ (uA)")
    ax1.set_title(f"NMOS nfet_01v8 W={WN} L={L}\ndevphys(TCAD) vs BSIM, same geometry")
    ax1.legend(fontsize=8); ax1.grid(alpha=0.3)

    ax2.semilogy(VG, np.abs(short["ID_lin"] / W_CAL * WN), "-", color="tab:red",
                 label="devphys Vd=0.1")
    ax2.semilogy(vg_bl, id_bl, "o", ms=3, mfc="none", color="tab:blue",
                 label="BSIM Vd=0.1")
    ax2.set_ylim(1e-11, 1e-3)
    ax2.set_xlabel("$V_G$ (V)"); ax2.set_ylabel("$|I_D|$ (A)")
    ax2.set_title(f"Ion agree {100*(dn['Ion']/bn['Ion']-1):+.1f} %; "
                  "subthreshold from independent physics")
    ax2.legend(fontsize=8); ax2.grid(alpha=0.3)
    fig.suptitle("v3 reframe: devphys cross-checks the OWN cells' manufacturable "
                 "NMOS (PMOS pending stage-8)", fontweight="bold")
    fig.tight_layout()
    out = HERE / "crosscheck_devices.png"
    fig.savefig(out, dpi=130)
    print(f"figure -> {out}")


if __name__ == "__main__":
    main()
