"""Step 1: measure the devices, derive the sizing rules.

The P:N width ratio of every cell comes from MEASURED drive currents, not
folklore. We also compare the two PMOS flavors (svt vs hvt — the foundry
hd library uses hvt) and pick with stated reasoning.
"""
import json

from common import MODELS, OUT, VDD, TEMP, run_ngspice, parse_meas

DEVS = {
    "nfet": "sky130_fd_pr__nfet_01v8",
    "pfet_svt": "sky130_fd_pr__pfet_01v8",
    "pfet_hvt": "sky130_fd_pr__pfet_01v8_hvt",
}

results = {}
for name, model in DEVS.items():
    pol = -1 if "pfet" in name else 1
    net = f"""* {name} drive probe, W=1um L=0.15um
.lib "{MODELS}" tt
.temp {TEMP}
.option TEMP={TEMP}
vd d 0 {pol * VDD}
vg g 0 {pol * VDD}
xm d g 0 0 {model} w=1 l=0.15
.control
op
let idrv = abs(i(vd))
echo idrv_meas = $&idrv
.endc
.end
"""
    out = run_ngspice(net, f"probe_{name}")
    vals = parse_meas(out)
    results[name] = vals.get("idrv_meas", float("nan"))
    print(f"{name:9s} ({model}): |Id| = {results[name]*1e6:8.1f} uA/um "
          f"at |Vgs|=|Vds|={VDD} V")

ratio_svt = results["nfet"] / results["pfet_svt"]
ratio_hvt = results["nfet"] / results["pfet_hvt"]
print(f"\ndrive ratios n/p: svt {ratio_svt:.2f}, hvt {ratio_hvt:.2f}")
print("decision: svt PMOS — better drive per um lets the library hit "
      "symmetric rise/fall with less width (the foundry hd library chose "
      "hvt for leakage; at 921 cells and hobby duty cycles we trade "
      "leakage for area/speed — a DESIGN CHOICE, documented).")

sizing = {
    "L": 0.15,
    "WN_X1": 0.65,
    "WP_over_WN": round(ratio_svt, 2),
    "pfet_model": DEVS["pfet_svt"],
    "nfet_model": DEVS["nfet"],
    "idsat_n_uA_per_um": results["nfet"] * 1e6,
    "idsat_p_uA_per_um": results["pfet_svt"] * 1e6,
}
(OUT / "sizing.json").write_text(json.dumps(sizing, indent=1))
print(f"\nsizing rules -> {OUT / 'sizing.json'}: WN_X1=0.65um, "
      f"WP = {sizing['WP_over_WN']}x WN, L=0.15um everywhere")
