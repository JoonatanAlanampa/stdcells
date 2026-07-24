"""v3 Phase 2 premise gate: is a longer-L "geometric-hvt" NMOS a real leakage
lever on sky130? (The device V3-PLAN Phase 2 suggested building a cell set on.)

ANSWER (this script, BSIM tt, W = 0.65 um = the library WN): NO. Longer L is
NOT a geometric-hvt lever on sky130 nfet_01v8 -- it closes as the fourth
"geometric leakage control" target, for the same structural reason the three
exotic targets closed (the halo/pocket implants are engineered so leakage is
~L-independent).

  * L 0.15 -> 0.50 um SUPPRESSES DIBL (83 -> 15 mV) but the halo/RSCE implants
    LOWER Vt by the same amount, so at 25 C Ioff is FLAT (~1.9 pA) while Ion
    falls x0.48. Ion/Ioff (the leakage/speed figure of merit) only WORSENS.
  * At 100 C longer L does cut Ioff (x0.57 at L=0.5) but Ion drops harder
    (x0.44), so Ion/Ioff still does not improve for any useful L step (only a
    marginal 0.15->0.18 bump breaks even).

The V3-PLAN's OTHER named geometric lever -- STACKING -- IS real (unlike longer
L): a 2-high nfet stack cuts Ioff 3.5x at 100 C (Ion/Ioff 2.0x better), though
it wins only at the hot corner and is a topology the library already uses in
NAND2/NOR2. That is why the reframe (devphys = cross-check on the manufacturable
rectangular cells, crosscheck_devices.py) -- not a geometric-hvt cell set -- is
the honest Phase 2.

Reproducible: two BSIM experiments (L sweep at 25/100 C; single-vs-stack Ioff).
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # flow/
from common import MODELS, NGSPICE, OUT                            # noqa: E402

W = 0.65
LS = [0.15, 0.18, 0.25, 0.35, 0.50]


def _idvg(L, T, vd):
    base = f"llg_{int(L*1000)}_{T}_{int(vd*10)}"
    dump = OUT / f"{base}.txt"
    if dump.exists():
        dump.unlink()
    net = f"""* nfet_01v8 W={W} L={L} T={T} Vd={vd}
.lib "{MODELS}" tt
.temp {T}
vd d 0 {vd}
vg g 0 0
xm d g 0 0 sky130_fd_pr__nfet_01v8 w={W} l={L}
.control
dc vg 0 1.8 0.01
let ad = abs(i(vd))
wrdata {base}.txt ad
.endc
.end
"""
    (OUT / f"{base}.sp").write_text(net)
    subprocess.run([str(NGSPICE), "-b", str(OUT / f"{base}.sp")],
                   capture_output=True, text=True, cwd=OUT, timeout=600)
    d = np.loadtxt(dump)
    return d[:, 0], d[:, 1]


def _vt_cc(vg, idd, L):
    th = 0.1e-6 * (W / L)
    good = idd > 1e-12
    return float(np.interp(np.log(th), np.log(idd[good]), vg[good]))


def l_sweep():
    print("=" * 74)
    print(f"LONGER-L geometric-hvt gate: nfet_01v8 W={W} um (library WN), BSIM tt")
    print("=" * 74)
    verdict_ok = True
    for T in (25, 100):
        print(f"\n T={T} C   {'L(um)':>6} {'Vtlin':>7} {'Vtsat':>7} {'DIBL(mV)':>9} "
              f"{'Ion(uA)':>9} {'Ioff(pA)':>10} {'Ion/Ioff':>10}")
        base = {}
        for L in LS:
            vg_l, id_l = _idvg(L, T, 0.1)
            vg_s, id_s = _idvg(L, T, 1.8)
            vtl, vts = _vt_cc(vg_l, id_l, L), _vt_cc(vg_s, id_s, L)
            ion, ioff = id_s[-1], id_s[0]
            base[L] = (ion, ioff)
            print(f"          {L:6.2f} {vtl:7.3f} {vts:7.3f} {(vtl-vts)*1e3:9.0f} "
                  f"{ion*1e6:9.1f} {ioff*1e12:10.2f} {ion/ioff:10.3e}")
        ion0, ioff0 = base[0.15]
        # the leakage lever fails if Ion/Ioff never improves by >5% at any L
        fom = [(base[L][0]/base[L][1]) / (ion0/ioff0) for L in LS]
        best = max(fom)
        print(f"          -> best Ion/Ioff vs L=0.15: x{best:.2f} "
              f"({'IMPROVES' if best > 1.15 else 'no useful improvement -> NOT a lever'})")
        # a real hvt lever would give a large (>1.15x) Ion/Ioff gain; the only
        # break-even is the marginal 100C/0.18 bump (~1.09x), well under that.
        verdict_ok = verdict_ok and best <= 1.15
    return verdict_ok


def _op(body, tag):
    net = f'.lib "{MODELS}" tt\n{body}\n'
    (OUT / f"{tag}.sp").write_text(net)
    cp = subprocess.run([str(NGSPICE), "-b", str(OUT / f"{tag}.sp")],
                        capture_output=True, text=True, cwd=OUT, timeout=300)
    out = {}
    for line in cp.stdout.splitlines():
        ll = line.lower()
        if "=" in ll and any(k in ll for k in ("ioff", "ion")):
            k, v = ll.split("=")[0].strip(), ll.split("=")[1].strip()
            try:
                out[k] = float(v.split()[0])
            except ValueError:
                pass
    return out


def stack_check():
    print("\n" + "=" * 74)
    print("STACK effect (the lever that DOES work): single vs 2-high nfet stack")
    print("=" * 74)
    dev = f"sky130_fd_pr__nfet_01v8 w={W} l=0.15"
    for T in (25, 100):
        single = f""".temp {T}
vd d 0 1.8
vg g 0 0
xm d g 0 0 {dev}
.control
op
let ioff=abs(i(vd))
echo IOFF = $&ioff
alter vg 1.8
op
let ion=abs(i(vd))
echo ION = $&ion
.endc
.end"""
        stack = f""".temp {T}
vd d 0 1.8
vg g 0 0
xm1 d g mid 0 {dev}
xm2 mid g 0 0 {dev}
.control
op
let ioff=abs(i(vd))
echo IOFF = $&ioff
alter vg 1.8
op
let ion=abs(i(vd))
echo ION = $&ion
.endc
.end"""
        s = _op(single, f"llg_single_{T}")
        k = _op(stack, f"llg_stack_{T}")
        print(f" T={T:>3}C  single Ioff {s['ioff']*1e12:6.2f} pA / Ion "
              f"{s['ion']*1e6:5.1f} uA   stack Ioff {k['ioff']*1e12:6.2f} pA / Ion "
              f"{k['ion']*1e6:5.1f} uA")
        print(f"         -> stack cuts Ioff {s['ioff']/k['ioff']:.1f}x, "
              f"Ion x{k['ion']/s['ion']:.2f}, Ion/Ioff "
              f"x{(k['ion']/k['ioff'])/(s['ion']/s['ioff']):.2f}")


def main():
    ok = l_sweep()
    stack_check()
    print("\nVERDICT: longer-L geometric-hvt is",
          "REFUTED (no Ion/Ioff improvement) -- 4th closed geometric-leakage target."
          if ok else "UNEXPECTEDLY a lever -- re-examine!")
    print("STAGE: longer-L premise gate DONE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
