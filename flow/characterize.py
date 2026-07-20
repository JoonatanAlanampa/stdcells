"""Step 3: characterize the library with ngspice -> our own Liberty file.

Measured per cell, by us, from transistor-level transient simulation with
the sky130 tt models at 25C/1.8V:
  - input capacitance per pin (charge integration)
  - NLDM delay (50/50) + output transition (20/80) tables, 3 slews x 3
    loads, both edges, per input arc
  - DFF: CLK->Q tables, setup and hold by bisection
  - leakage (all-inputs-low state)
"""
import itertools
import sys

import numpy as np

from common import MODELS, OUT, VDD, TEMP, run_ngspice, parse_meas
from cells import LIBRARY

SLEWS = [0.05e-9, 0.3e-9, 1.5e-9]      # input transition, 20-80, seconds
LOADS = [5e-15, 25e-15, 100e-15]       # output load, farads
T_END = 40e-9

HDR = f'.lib "{MODELS}" tt\n.temp {TEMP}\n.option TEMP={TEMP}\n'


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
    vals = parse_meas(run_ngspice(net, f"cin_{cell.name}_{pin}"))
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
    vals = parse_meas(run_ngspice(net, f"leak_{cell.name}"))
    return vals.get("ileak_meas", 0.0) * VDD          # watts


def dff_clkq(cell, slew, load, tag):
    ramp = slew / 0.6
    net = f"""* DFF clk->q slew={slew} load={load}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
vd D 0 pulse(0 {VDD} 1n 0.1n 0.1n 19n 40n)
vc CLK 0 pulse(0 {VDD} 5n {ramp} {ramp} 8n 16n)
xdut D CLK Q vdd vss {cell.name}
cload Q 0 {load}
.tran 2p 40n
.control
run
meas tran tcqr trig v(CLK) val={VDD/2} rise=1 targ v(Q) val={VDD/2} rise=1
meas tran tcqf trig v(CLK) val={VDD/2} rise=2 targ v(Q) val={VDD/2} fall=1
meas tran trq1 trig v(Q) val={0.2*VDD} rise=1 targ v(Q) val={0.8*VDD} rise=1
meas tran trq2 trig v(Q) val={0.8*VDD} fall=1 targ v(Q) val={0.2*VDD} fall=1
.endc
.end
"""
    return parse_meas(run_ngspice(net, tag))


def dff_setup(cell):
    """Bisection: latest D-rise before the CLK edge that still captures."""
    lo, hi = 0.0, 1.0e-9               # D leads CLK by t: works at 1 ns
    clk_edge = 10e-9
    for _ in range(12):
        t = (lo + hi) / 2
        net = f"""* DFF setup probe t={t}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
vd D 0 pwl(0 0 {clk_edge - t} 0 {clk_edge - t + 0.05e-9} {VDD})
vc CLK 0 pulse(0 {VDD} {clk_edge} 0.1n 0.1n 5n 20n)
xdut D CLK Q vdd vss {cell.name}
cload Q 0 25f
.tran 2p 18n
.control
run
meas tran qfin find v(Q) at=15n
.endc
.end
"""
        vals = parse_meas(run_ngspice(net, "dff_setup_probe"))
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
          index_2("{', '.join(f'{c*1e15:.1f}' for c in LOADS)}");
          values({v.rstrip(',')});
        }}"""


print("characterizing", len(LIBRARY), "cells ...")
lib_cells = []
for cell in LIBRARY:
    caps = {p: input_cap(cell, p) for p in cell.inputs}
    leak = leakage(cell)
    if cell.clocked:
        tables = {k: np.zeros((3, 3)) for k in ("tcqr", "tcqf", "trq1", "trq2")}
        for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                enumerate(LOADS)):
            m = dff_clkq(cell, s, c, f"dffq_{i}{j}")
            for k in tables:
                tables[k][i, j] = m.get(k, np.nan)
        tsu = dff_setup(cell)
        lib_cells.append((cell, caps, leak, {"clkq": tables, "setup": tsu}))
        print(f"  {cell.name}: clk-q {tables['tcqr'][1,1]*1e12:.0f} ps @mid, "
              f"setup {tsu*1e12:.0f} ps, cin(D) {caps['D']*1e15:.2f} fF")
    else:
        arcs = {}
        for pin in cell.inputs:
            t = {k: np.zeros((3, 3)) for k in ("tdr", "tdf", "trout1", "trout2")}
            for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                    enumerate(LOADS)):
                m = arc_run(cell, pin, s, c, f"arc_{cell.name}_{pin}_{i}{j}")
                for k in t:
                    t[k][i, j] = m.get(k, np.nan)
            arcs[pin] = t
        lib_cells.append((cell, caps, leak, arcs))
        mid = arcs[cell.inputs[0]]["tdr"][1, 1]
        print(f"  {cell.name}: tp {mid*1e12:.0f} ps @mid, "
              f"cin {caps[cell.inputs[0]]*1e15:.2f} fF, leak {leak*1e12:.1f} pW")

# ------------------------------------------------------------- liberty out
L = []
L.append(f"""library (own_sky130) {{
  technology (cmos);
  delay_model : table_lookup;
  time_unit : "1ns"; voltage_unit : "1V"; current_unit : "1mA";
  pulling_resistance_unit : "1kohm"; capacitive_load_unit (1, pf);
  leakage_power_unit : "1nW";
  nom_process : 1; nom_voltage : {VDD}; nom_temperature : {TEMP};
  operating_conditions (tt) {{ process : 1; voltage : {VDD}; temperature : {TEMP}; }}
  default_operating_conditions : tt;
  slew_lower_threshold_pct_rise : 20; slew_upper_threshold_pct_rise : 80;
  slew_lower_threshold_pct_fall : 20; slew_upper_threshold_pct_fall : 80;
  input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;
  output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;
  lu_table_template (tbl33) {{
    variable_1 : input_net_transition; variable_2 : total_output_net_capacitance;
    index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
    index_2("{', '.join(f'{c*1e15:.1f}' for c in LOADS)}");
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
      max_capacitance : {LOADS[-1]*1e12:.3f};
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
        L.append(f"      max_capacitance : {LOADS[-1]*1e12:.3f};")
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
(OUT / "own.lib").write_text("\n".join(L))
print(f"\nwrote {OUT / 'own.lib'}")

bad = []
for cell, caps, leak, data in lib_cells:
    tabs = data["clkq"].values() if "setup" in data else \
        [t for arc in data.values() for t in arc.values()]
    if any(np.isnan(t).any() for t in tabs):
        bad.append(cell.name)
if bad:
    sys.exit(f"NaN in characterization tables for {bad} — inspect out/*.log")
print("CHARACTERIZATION COMPLETE")
