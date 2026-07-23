"""devphys characterization of the off-bin W=0.25 um NMOS -- where BSIM cannot.

The v3 task: characterize the pinned off-bin device via devphys TCAD (stages
4-5), "since BSIM can't". This does exactly that -- and reports the honest
result, which is sharper than the task assumed.

THREE COINCIDING WALLS at (W=0.25 um, L=0.15 um), all proven, not asserted:
  1. magic diff/tap.2 FORBIDS building it   (offbin.yml CI; < 0.42 um std floor)
  2. BSIM ngspice REFUSES to model it        ("could not find a valid modelname"
                                              -- no bin at (0.25, 0.15); see below)
  3. measured silicon shows NO narrow-width effect to model
                                              (devphys Phase-0, 07_nfet_3d)

devphys CAN still emit an I-V here, because its stage-4c nfet is 2D: current is
computed PER UNIT WIDTH and multiplied by W (mosfet_short.py:280,
`(In+Ip)*WIDTH_CM`). So "devphys at W=0.25" is IDENTICALLY the silicon-calibrated
per-um physics x 0.25 -- real numbers where BSIM returns none, but pure
width-scaling with no narrow-W content (consistent with wall 3). That is
devphys's REACH, not a physical gap it uniquely fills.

The REFRAMED value (what the grand goal actually needs): devphys reproduces
BSIM at a MANUFACTURABLE width from silicon-calibrated physics -- an independent
from-physics characterization of the cells you CAN build. Shown here at the
W=0.42 um diff/tap.2 floor (the narrowest legal logic NMOS), where both exist.

Reads the committed devphys short-channel solve (devphys/04_sky130_nfet/
short_results.npz, L=0.15 um, calibrated to measured W=25 um silicon) and runs
BSIM ngspice locally. Local-only (not CI): devphys is a sibling repo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import MODELS, run_ngspice, parse_meas

HERE = Path(__file__).resolve().parent
DEVPHYS = Path(__file__).resolve().parents[3] / "devphys" / "04_sky130_nfet"
NPZ = DEVPHYS / "short_results.npz"

W_OFF = 0.25       # off-bin target
W_FLOOR = 0.42     # diff/tap.2 std floor = narrowest legal logic NMOS (in-bin)
W_CAL = 25.0       # devphys solve width (2D model; W is a scalar multiplier)
L = 0.15


def extract_vt(vg, idlin, vd=0.1):
    """max-gm linear-extrapolation Vt."""
    gm = np.gradient(idlin, vg)
    i = int(np.argmax(gm))
    return vg[i] - idlin[i] / gm[i] - vd / 2


def bsim_drive(w, vg=1.8, vd=1.8):
    """BSIM ngspice |Id| at (w, L=0.15). Returns None if off-bin (no model)."""
    net = f"""* nfet_01v8 W={w} L={L}
.lib "{MODELS}" tt
.temp 25
.option TEMP={25}
vd d 0 {vd}
vg g 0 {vg}
xm d g 0 0 sky130_fd_pr__nfet_01v8 w={w} l={L}
.control
op
let idrv = abs(i(vd))
echo IDRVMEAS = $&idrv
.endc
.end
"""
    out = run_ngspice(net, f"dpx_{int(w*1000)}")
    if "could not find a valid modelname" in out:
        return None
    return parse_meas(out).get("idrvmeas")


def main():
    if not NPZ.exists():
        sys.exit(f"devphys solve not found: {NPZ}\n"
                 "run devphys/04_sky130_nfet/mosfet_short.py first (or clone devphys).")
    d = np.load(NPZ)
    VG, ID_lin, ID_sat = d["VG"], d["ID_lin"], d["ID_sat"]
    sat_grid = d["sat_grid"]

    # per-um, silicon-calibrated at L=0.15 (the whole 2D-model point: /W)
    perum_lin = ID_lin / W_CAL
    perum_sat = ID_sat / W_CAL
    ion_perum = float(perum_sat[np.argmax(sat_grid)])          # Vg=Vd=1.8
    vt_dp = extract_vt(VG, ID_lin, 0.1)

    print("=" * 74)
    print("devphys characterization of the OFF-BIN W=0.25 um NMOS (L=0.15 um)")
    print("=" * 74)
    print(f"devphys per-um (silicon-calibrated, L=0.15): Ion = {ion_perum*1e6:.1f} "
          f"uA/um at Vg=Vd=1.8 V; Vt(max-gm) = {vt_dp:.3f} V")
    print()
    print(f"  -> devphys Id for the off-bin W={W_OFF} um device (width-scaled):")
    print(f"       Ion = {ion_perum*W_OFF*1e6:.1f} uA   (BSIM: NO MODEL -- refuses)")
    print(f"     devphys Id for the W={W_FLOOR} um floor control (width-scaled):")
    print(f"       Ion = {ion_perum*W_FLOOR*1e6:.1f} uA")
    print()

    # --- the bracket table: DRC / model / drive at each width -----------
    print(f"{'W(um)':>6} {'KLayout':>8} {'magic dt.2':>11} {'BSIM Id':>10} "
          f"{'devphys Id':>11}  note")
    rows = [
        (0.25, "clean", "FORBID", None, "off-bin: 3 walls (build/model/physics)"),
        (0.36, "clean", "FORBID", None, "off-bin at L=0.15 (lowest bin W=0.39)"),
        (0.42, "clean", "ok",     None, "narrowest LEGAL logic NMOS (in-bin)"),
        (0.65, "clean", "ok",     None, "typical logic NFET"),
        (1.00, "clean", "ok",     None, "wide NFET"),
    ]
    cross = {}
    for i, (w, kl, dt, _b, note) in enumerate(rows):
        bid = bsim_drive(w)
        dpid = ion_perum * w
        bs = f"{bid*1e6:8.1f}u" if bid else "  refuse"
        if bid:
            cross[w] = (bid, dpid)
        print(f"{w:6.2f} {kl:>8} {dt:>11} {bs:>10} {dpid*1e6:9.1f}u  {note}")

    # --- reframed value: devphys vs BSIM where BOTH exist ---------------
    print("\nCROSS-CHECK (the reframed devphys value -- own physics vs BSIM at a")
    print("manufacturable geometry; both silicon-referenced):")
    for w in (0.42, 0.65, 1.0):
        if w in cross:
            bid, dpid = cross[w]
            print(f"  W={w:>4} um: BSIM {bid*1e6:6.1f} uA  vs  devphys {dpid*1e6:6.1f} "
                  f"uA   ({100*(dpid/bid-1):+.1f} %)")

    # --- figure ---------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    # left: devphys Id-Vg at W=0.25 (off-bin) and W=0.42 (floor)
    ax1.plot(VG, ID_lin / W_CAL * W_OFF * 1e6, "-", color="tab:red",
             label=f"devphys W={W_OFF} (OFF-BIN: BSIM refuses)")
    ax1.plot(VG, ID_lin / W_CAL * W_FLOOR * 1e6, "-", color="tab:blue",
             label=f"devphys W={W_FLOOR} (floor, in-bin)")
    ax1.axvline(vt_dp, ls=":", color="gray", lw=1)
    ax1.set_xlabel("$V_G$ (V)"); ax1.set_ylabel("$I_D$ (uA)  [$V_D$=0.1 V]")
    ax1.set_title("devphys emits I-V where BSIM has no model\n"
                  "(width-scaled per-um physics, L=0.15 um)")
    ax1.legend(fontsize=8); ax1.grid(alpha=0.3)

    # right: drive vs width, devphys line + BSIM points, walls marked
    ws = np.linspace(0.15, 1.05, 50)
    ax2.plot(ws, ion_perum * ws * 1e6, "-", color="tab:red",
             label="devphys (per-um x W)")
    bw = [w for w in (0.42, 0.65, 1.0) if w in cross]
    ax2.plot(bw, [cross[w][0] * 1e6 for w in bw], "o", ms=8, color="tab:blue",
             label="BSIM ngspice (in-bin only)")
    ax2.axvspan(0.15, 0.42, color="tab:orange", alpha=0.12)
    ax2.axvline(0.42, ls="--", color="k", lw=1)
    ax2.text(0.16, ax2.get_ylim()[1] * 0.9,
             "magic diff/tap.2 forbids\nBSIM has no bin\n(W < 0.42 um)",
             fontsize=8, va="top")
    ax2.plot([W_OFF], [ion_perum * W_OFF * 1e6], "*", ms=15, color="tab:red")
    ax2.set_xlabel("channel width W (um)"); ax2.set_ylabel("$I_{on}$ (uA) @ Vg=Vd=1.8")
    ax2.set_title("both walls at W=0.42: BSIM stops modeling\n"
                  "exactly where the foundry stops allowing")
    ax2.legend(fontsize=8, loc="lower right"); ax2.grid(alpha=0.3)

    fig.suptitle("Off-bin W=0.25 um NMOS: devphys reaches it, BSIM refuses, "
                 "magic forbids", fontweight="bold")
    fig.tight_layout()
    out = HERE / "devphys_offbin.png"
    fig.savefig(out, dpi=130)
    print(f"\nfigure -> {out}")
    print("STAGE: devphys off-bin characterization DONE")


if __name__ == "__main__":
    main()
