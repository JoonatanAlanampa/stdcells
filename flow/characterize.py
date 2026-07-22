"""Step 3: characterize the library with ngspice -> our own Liberty files.

Measured per cell, by us, from transistor-level transient simulation:
  - input capacitance per pin (charge integration)
  - NLDM delay (50/50) + output transition (20/80) tables, 3 slews x 3
    loads, both edges, per input arc
  - DFF: CLK->Q tables, setup and hold by bisection
  - leakage (all-inputs-low state)

MULTI-PVT (lib-v1.1). Everything is re-measured at each of the three corners
the sky130A flow signs off on, so the timing views actually DIFFER:

    tt_025C_1v80   nominal
    ss_100C_1v60   slow silicon, hot, low rail  -> the setup corner
    ff_n40C_1v95   fast silicon, cold, high rail -> the hold corner

Why this matters beyond signoff hygiene: the vertical-slice chip exists to
measure ring-oscillator delay in silicon and compare it against what this
library predicts. Characterized at one PVT, every SDF corner came out
byte-identical, so a measured-vs-predicted gap had no error bar to be judged
against and could not be attributed to process, temperature or voltage. A
corner spread turns that comparison into a real measurement.

The PVT is carried in module globals that the netlist builders read at call
time, so set_pvt() is all it takes -- no netlist code is PVT-aware.
"""
import itertools
import sys

import numpy as np

from common import MODELS, OUT, VDD, TEMP, run_ngspice, parse_meas
from cells import LIBRARY

SLEWS = [0.05e-9, 0.3e-9, 1.5e-9]      # input transition, 20-80, seconds
LOADS = [5e-15, 25e-15, 100e-15]       # output load, farads
T_END = 40e-9

# (liberty/PDK corner name, model section, volts, celsius)
PVTS = [
    ("tt_025C_1v80", "tt", 1.80, 25),
    ("ss_100C_1v60", "ss", 1.60, 100),
    ("ff_n40C_1v95", "ff", 1.95, -40),
]
NOM = PVTS[0][0]

HDR = f'.lib "{MODELS}" tt\n.temp {TEMP}\n.option TEMP={TEMP}\n'
CORNER = NOM


def set_pvt(corner, section, vdd, temp):
    """Point every subsequent ngspice run at one process/voltage/temperature."""
    global VDD, TEMP, HDR, CORNER
    VDD, TEMP, CORNER = vdd, temp, corner
    HDR = f'.lib "{MODELS}" {section}\n.temp {temp}\n.option TEMP={temp}\n'


def noncontrolling(cell, active_pin):
    """Values for the other inputs so the active pin controls the output."""
    vals = {}
    for p in cell.inputs:
        if p == active_pin:
            continue
        vals[p] = VDD if "&" in (cell.function or "") or cell.function in \
            ("(!A)", "A") else 0.0
    return vals


def arc_run(cell, pin, slew, load, tag):
    """One transient: pin pulses low-high-low; measure both arcs."""
    others = noncontrolling(cell, pin)
    src = [f"v{p} {p} 0 {v}" for p, v in others.items()]
    ramp = slew / 0.6                   # 20-80 -> 0-100 ramp time
    net = f"""* {cell.name} arc {pin} slew={slew} load={load}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
{chr(10).join(src)}
vin {pin} 0 pulse(0 {VDD} 2n {ramp} {ramp} 15n 40n)
xdut {" ".join(cell.inputs + [cell.output])} vdd vss {cell.name}
cload {cell.output} 0 {load}
.tran 2p {T_END}
.control
run
meas tran tdr trig v({pin}) val={VDD/2} rise=1 targ v({cell.output}) val={VDD/2} cross=1
meas tran tdf trig v({pin}) val={VDD/2} fall=1 targ v({cell.output}) val={VDD/2} cross=2
meas tran trout1 trig v({cell.output}) val={0.2*VDD} cross=1 targ v({cell.output}) val={0.8*VDD} cross=1
meas tran trout2 trig v({cell.output}) val={0.8*VDD} cross=2 targ v({cell.output}) val={0.2*VDD} cross=2
.endc
.end
"""
    vals = parse_meas(run_ngspice(net, tag))
    return vals


def input_cap(cell, pin):
    others = noncontrolling(cell, pin)
    src = [f"v{p} {p} 0 {v}" for p, v in others.items()]
    net = f"""* {cell.name} cin {pin}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
{chr(10).join(src)}
vin {pin} 0 pulse(0 {VDD} 2n 1n 1n 10n 30n)
xdut {" ".join(cell.inputs + [cell.output])} vdd vss {cell.name}
.tran 5p 12n
.control
run
meas tran qin integ i(vin) from=1.5n to=8n
echo qin_meas = $&qin
.endc
.end
"""
    vals = parse_meas(run_ngspice(net, f"cin_{CORNER}_{cell.name}_{pin}"))
    q = abs(vals.get("qin_meas", 0.0))
    return q / VDD


def leakage(cell):
    src = [f"v{p} {p} 0 0" for p in cell.inputs]
    net = f"""* {cell.name} leakage
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
{chr(10).join(src)}
xdut {" ".join(cell.inputs + [cell.output])} vdd vss {cell.name}
.control
op
let il = abs(i(vdd))
echo ileak_meas = $&il
.endc
.end
"""
    vals = parse_meas(run_ngspice(net, f"leak_{CORNER}_{cell.name}"))
    return vals.get("ileak_meas", 0.0) * VDD          # watts


def _dff_edge(cell, slew, load, tag, rising):
    """One clk->Q capture, measured so the answer cannot depend on power-up.

    A flip-flop with no reset powers up in whichever state ngspice's OP settles
    -- at ff that was Q=1, which first made the rising capture go NaN, and then
    (once a reset edge was added) made a `fall=1` measurement latch onto the
    reset's own falling glitch instead of the capture. Both are the same
    disease: a Q transition whose existence depends on the power-up state.

    The cure is to precondition Q into the OPPOSITE of what is being measured,
    with a real clocked edge:
      rising  capture -> reset Q=0 first; the reset can only make Q FALL, so the
                         single Q RISE in the run is unambiguously the capture.
      falling capture -> set   Q=1 first; the set can only make Q RISE, so the
                         single Q FALL is unambiguously the capture.
    Clock edges: #1 precondition (2 ns, sharp), #2 capture (8 ns, swept slew).
    """
    r = slew / 0.6                         # 20-80 slew -> 0-100 ramp
    if rising:
        d_pwl = "0 0 5n 0 5.1n {v} 12n {v}".format(v=VDD)   # low, then high
    else:
        d_pwl = "0 {v} 5n {v} 5.1n 0 12n 0".format(v=VDD)   # high, then low
    net = f"""* DFF clk->q {'rise' if rising else 'fall'} slew={slew} load={load}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
vd D 0 pwl({d_pwl})
vc CLK 0 pwl(0 0  2n 0 2.1n {VDD}  4n {VDD} 4.1n 0
+  8n 0 {8e-9+r} {VDD}  11n {VDD} {11e-9+r} 0)
xdut D CLK Q vdd vss {cell.name}
cload Q 0 {load}
.tran 2p 13n
.control
run
meas tran tcq trig v(CLK) val={VDD/2} rise=2 targ v(Q) val={VDD/2} """ + (
        "rise=1" if rising else "fall=1") + f"""
meas tran ttr1 trig v(Q) val={0.2*VDD} rise=1 targ v(Q) val={0.8*VDD} rise=1
meas tran ttr2 trig v(Q) val={0.8*VDD} fall=1 targ v(Q) val={0.2*VDD} fall=1
.endc
.end
"""
    return parse_meas(run_ngspice(net, tag))


def dff_clkq(cell, slew, load, tag):
    """CLK->Q for both edges, each from its own preconditioned run.

    Returns the same keys the caller expects (tcqr/tcqf clk-q delays, trq1/trq2
    output transitions), so nothing downstream changes.
    """
    up = _dff_edge(cell, slew, load, tag + "_r", rising=True)
    dn = _dff_edge(cell, slew, load, tag + "_f", rising=False)
    return {"tcqr": up.get("tcq"), "trq1": up.get("ttr1"),
            "tcqf": dn.get("tcq"), "trq2": dn.get("ttr2")}


def dff_setup(cell):
    """Bisection: latest D-rise before the CLK edge that still captures.

    Same power-up hazard as dff_clkq: without a reset a flop that settles high
    reads as "captured" for every trial and the bisection collapses to ~0 (the
    bogus 'setup 0 ps' seen at ff). A reset edge at 3 ns forces Q=0 first, so
    qfin>VDD/2 at the end means the capture edge genuinely wrote a 1.
    """
    lo, hi = 0.0, 1.0e-9               # D leads CLK by t: works at 1 ns
    clk_edge = 12e-9
    for _ in range(12):
        t = (lo + hi) / 2
        net = f"""* DFF setup probe t={t}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
vd D 0 pwl(0 0 {clk_edge - t} 0 {clk_edge - t + 0.05e-9} {VDD})
vc CLK 0 pwl(0 0 3n 0 3.1n {VDD} 5n {VDD} 5.1n 0
+  {clk_edge} 0 {clk_edge+0.1e-9} {VDD} {clk_edge+5e-9} {VDD} {clk_edge+5.1e-9} 0)
xdut D CLK Q vdd vss {cell.name}
cload Q 0 25f
.tran 2p {clk_edge + 7e-9}
.control
run
meas tran qfin find v(Q) at={clk_edge + 5e-9}
.endc
.end
"""
        vals = parse_meas(run_ngspice(net, f"dff_setup_probe_{CORNER}"))
        if vals.get("qfin", 0.0) > VDD / 2:
            hi = t                      # captured -> can push closer
        else:
            lo = t
    return hi


def table(name, rows):
    """rows[slew][load] -> liberty NLDM block (values in ns)."""
    v = " \\\n           ".join(
        '"' + ", ".join(f"{x*1e9:.5f}" for x in row) + '",' for row in rows)
    return f"""        {name} (tbl33) {{
          index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
          index_2("{', '.join(f'{c*1e12:.3f}' for c in LOADS)}");
          values({v.rstrip(',')});
        }}"""


# real layout areas override the projected site model where cells exist
import json
_ar = OUT / "areas_real.json"
if _ar.exists():
    real = json.loads(_ar.read_text())
    for c in LIBRARY:
        if c.name in real:
            c.area = real[c.name]

def characterize_all():
    """Measure every cell at the PVT currently set. Returns the lib_cells list."""
    print(f"characterizing {len(LIBRARY)} cells at {CORNER} "
          f"({VDD} V, {TEMP} C) ...")
    lib_cells = []
    for cell in LIBRARY:
        caps = {p: input_cap(cell, p) for p in cell.inputs}
        leak = leakage(cell)
        if cell.clocked:
            tables = {k: np.zeros((3, 3))
                      for k in ("tcqr", "tcqf", "trq1", "trq2")}
            for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                    enumerate(LOADS)):
                m = dff_clkq(cell, s, c, f"dffq_{CORNER}_{i}{j}")
                for k in tables:
                    tables[k][i, j] = m.get(k, np.nan)
            tsu = dff_setup(cell)
            lib_cells.append((cell, caps, leak, {"clkq": tables, "setup": tsu}))
            print(f"  {cell.name}: clk-q {tables['tcqr'][1,1]*1e12:.0f} ps @mid, "
                  f"setup {tsu*1e12:.0f} ps, cin(D) {caps['D']*1e15:.2f} fF")
        else:
            arcs = {}
            for pin in cell.inputs:
                t = {k: np.zeros((3, 3))
                     for k in ("tdr", "tdf", "trout1", "trout2")}
                for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                        enumerate(LOADS)):
                    m = arc_run(cell, pin, s, c,
                                f"arc_{CORNER}_{cell.name}_{pin}_{i}{j}")
                    for k in t:
                        t[k][i, j] = m.get(k, np.nan)
                arcs[pin] = t
            lib_cells.append((cell, caps, leak, arcs))
            mid = arcs[cell.inputs[0]]["tdr"][1, 1]
            print(f"  {cell.name}: tp {mid*1e12:.0f} ps @mid, "
                  f"cin {caps[cell.inputs[0]]*1e15:.2f} fF, "
                  f"leak {leak*1e12:.1f} pW")
    return lib_cells


def emit_liberty(lib_cells):
    """Render the measured data as a Liberty file for the current PVT."""
    L = []
    L.append(f"""library (own_sky130_{CORNER}) {{
  technology (cmos);
  delay_model : table_lookup;
  time_unit : "1ns"; voltage_unit : "1V"; current_unit : "1mA";
  pulling_resistance_unit : "1kohm"; capacitive_load_unit (1, pf);
  leakage_power_unit : "1nW";
  nom_process : 1; nom_voltage : {VDD}; nom_temperature : {TEMP};
  operating_conditions ({CORNER}) {{ process : 1; voltage : {VDD}; temperature : {TEMP}; }}
  default_operating_conditions : {CORNER};
  slew_lower_threshold_pct_rise : 20; slew_upper_threshold_pct_rise : 80;
  slew_lower_threshold_pct_fall : 20; slew_upper_threshold_pct_fall : 80;
  input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;
  output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;
  lu_table_template (tbl33) {{
    variable_1 : input_net_transition; variable_2 : total_output_net_capacitance;
    index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
    index_2("{', '.join(f'{c*1e12:.3f}' for c in LOADS)}");
  }}
""")
    for cell, caps, leak, data in lib_cells:
        L.append(f"  cell ({cell.name}) {{")
        L.append(f"    area : {cell.area};")
        L.append(f"    cell_leakage_power : {leak*1e9:.6f};")
        if cell.clocked:
            L.append("    ff (IQ, IQN) { next_state : \"D\"; clocked_on : \"CLK\"; }")
            tsu = data["setup"] * 1e9
            L.append(f"""    pin (CLK) {{ direction : input; clock : true;
          capacitance : {caps['CLK']*1e12:.6f}; }}
        pin (D) {{ direction : input; capacitance : {caps['D']*1e12:.6f};
          timing () {{ related_pin : "CLK"; timing_type : setup_rising;
            rise_constraint (scalar) {{ values("{tsu:.5f}"); }}
            fall_constraint (scalar) {{ values("{tsu:.5f}"); }} }}
          timing () {{ related_pin : "CLK"; timing_type : hold_rising;
            rise_constraint (scalar) {{ values("0.0"); }}
            fall_constraint (scalar) {{ values("0.0"); }} }} }}
        pin (Q) {{ direction : output; function : "IQ";
          max_capacitance : {LOADS[-1]*1e12:.3f}; max_transition : {SLEWS[-1]*1e9:.3f};
          timing () {{ related_pin : "CLK"; timing_type : rising_edge;
    {table("cell_rise", data["clkq"]["tcqr"])}
    {table("rise_transition", data["clkq"]["trq1"])}
    {table("cell_fall", data["clkq"]["tcqf"])}
    {table("fall_transition", data["clkq"]["trq2"])} }} }}""")
        else:
            for p in cell.inputs:
                L.append(f"    pin ({p}) {{ direction : input; "
                         f"capacitance : {caps[p]*1e12:.6f}; }}")
            L.append(f"    pin ({cell.output}) {{ direction : output; "
                     f"function : \"{cell.function}\";")
            L.append(f"      max_capacitance : {LOADS[-1]*1e12:.3f}; max_transition : {SLEWS[-1]*1e9:.3f};")
            for p in cell.inputs:
                a = data[p]
                inverting = cell.function.startswith("(!")
                cr = a["tdf" if inverting else "tdr"]
                cf = a["tdr" if inverting else "tdf"]
                L.append(f"""      timing () {{ related_pin : "{p}";
            timing_sense : {"negative_unate" if inverting else "positive_unate"};
    {table("cell_rise", cr)}
    {table("rise_transition", a["trout1"])}
    {table("cell_fall", cf)}
    {table("fall_transition", a["trout2"])} }}""")
            L.append("    }")
        L.append("  }")
    L.append("}")
    return "\n".join(L)


def check_no_nan(lib_cells):
    bad = []
    for cell, caps, leak, data in lib_cells:
        tabs = data["clkq"].values() if "setup" in data else \
            [t for arc in data.values() for t in arc.values()]
        if any(np.isnan(t).any() for t in tabs):
            bad.append(cell.name)
    if bad:
        sys.exit(f"NaN in characterization tables for {bad} at {CORNER} "
                 f"— inspect out/*.log")


def run(wanted):
    """Characterize the requested corners, write their liberty files, and
    print the corner spread. `wanted` is a list of corner names."""
    summary = {}
    for corner, section, vdd, temp in PVTS:
        if corner not in wanted:
            continue
        set_pvt(corner, section, vdd, temp)
        cells_data = characterize_all()
        check_no_nan(cells_data)
        (OUT / f"own_{corner}.lib").write_text(emit_liberty(cells_data))
        if corner == NOM:
            # keep the historical filename pointing at the nominal corner so
            # every existing consumer (make_hardening, the abc/dfflibmap
            # copies) is untouched by this change
            (OUT / "own.lib").write_text(emit_liberty(cells_data))
        summary[corner] = {
            c.name: (d["clkq"]["tcqr"][1, 1] if c.clocked
                     else d[c.inputs[0]]["tdr"][1, 1], leak)
            for c, caps, leak, d in cells_data}
        print(f"wrote {OUT / f'own_{corner}.lib'}\n")

    if len(summary) > 1:
        print("=" * 66)
        print("CORNER SPREAD — mid-slew/mid-load delay, and leakage")
        print("=" * 66)
        names = sorted({n for s in summary.values() for n in s})
        hdr = "".join(f"{c:>16s}" for c in summary)
        print(f"{'cell':<12s}{hdr}{'ss/ff':>9s}")
        for n in names:
            row = "".join(f"{1e12*summary[c][n][0]:>10.1f} ps" for c in summary)
            sp = (summary.get("ss_100C_1v60", {}).get(n, (np.nan,))[0] /
                  summary.get("ff_n40C_1v95", {}).get(n, (np.nan,))[0])
            print(f"{n:<12s}{row}{sp:>9.2f}")
        lk = {c: sum(v[1] for v in summary[c].values()) for c in summary}
        print(f"\n{'total leakage':<12s}" +
              "".join(f"{1e9*lk[c]:>10.2f} nW" for c in lk))
        print("\nThe ss/ff delay ratio is the number that was missing: with "
              "one\nPVT it was 1.00 by construction, so silicon could not be "
              "compared\nagainst a spread. Setup signs off at ss, hold at ff.")
    return summary


if __name__ == "__main__":
    # `python characterize.py tt_025C_1v80` does one corner; no arg does all.
    run(sys.argv[1:] or [p[0] for p in PVTS])
    print("CHARACTERIZATION COMPLETE")
