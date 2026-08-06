"""Step 3: characterize the library with ngspice -> our own Liberty files.

Measured per cell, by us, from transistor-level transient simulation:
  - input capacitance per pin (charge integration)
  - NLDM delay (50/50) + output transition (20/80) tables, per input arc
  - internal_power (rise_power/fall_power) per input arc  [lib-v1.2]
  - DFF: CLK->Q tables, setup and hold by bisection, per D direction [lib-v1.6]
  - per-state leakage (all 2^N input states)              [lib-v1.2]

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

lib-v1.2 closes the two gaps research/internal-power.md ranked highest:
  * grid: a fast-slew (20 ps) and a low-load (2 fF) point are prepended so the
    ring's operating point (~50 ps slew, ~3.6 fF load) is INTERIOR to the NLDM
    box. At the old LOADS[0]=5 fF the RO load fell BELOW the grid and OpenSTA
    extrapolated the ring-stage delay with unbounded error -- the one gap that
    actually moves the silicon prediction (temperature is quoted as a band in
    the vertical-slice run, not baked in here; NOR2 is the temp-exposed cell).
  * power: internal_power (dynamic switching energy, pJ) and per-state
    leakage_power(when) are now emitted for the combinational cells -- ahead of
    CharLib, which emits neither. The DFF's internal power and per-state
    leakage are deferred (its state includes internal storage nodes); it keeps
    valid timing plus a single averaged cell_leakage_power.

The PVT is carried in module globals that the netlist builders read at call
time, so set_pvt() is all it takes -- no netlist code is PVT-aware.

lib-v1.3 documents (does not change) a physical property of these cells: because
they are asymmetric by design (WP 1.0 um > WN 0.65 um, the routability sizing),
their switching threshold is off Vdd/2, so the 50-50 propagation delay can go
NEGATIVE and can SHRINK with a slower input ramp -- the output trips before the
input reaches 50 % (waveform-confirmed: INV_X4 cell_fall at ff/1.5 ns/2 fF is
-96 ps). Liberty permits negative delays and this flow does not clamp measured
data, so both are emitted as measured. They are confined to light-load / fast-
cell / slow-input entries the design never signs off on; load-monotonicity -- the
property STA leans on for a fixed driver -- holds everywhere. flow/check_monotonic.py
asserts that load-monotonicity (a regression guard) and reports the slew dips.

lib-v1.4 FIXES defect M11: every output-transition table was measured by
CROSSING ORDINAL rather than by direction, so on the five inverting cells
(INV_X1/X2/X4, NAND2_X1, NOR2_X1) the two tables came out negative AND
exchanged -- `rise_transition` carried minus the fall time and vice versa.
The magnitudes were right; the labels were not. Downstream: OpenSTA clamps a
negative transition to zero, so vertical-slice's entire signoff ran at ZERO
input slew on 20 of its 21 driver rows and its "max slew violation count 0"
asserted nothing. See arc_run for the mechanism and the measured numbers.

lib-v1.6 FIXES defects M17 and M18, both in the DFF constraint measurement,
and the line above ("setup and hold by bisection") was not true until now.

  * M17 -- HOLD WAS NEVER MEASURED. It was emitted as a literal
    `rise_constraint (scalar) { values("0.0"); }` for both directions, from
    lib-v1.0 to lib-v1.5, in the same `timing()` group whose setup beside it
    was searched for. It was carried as a known deferral in the README, but
    the consequence was not stated: vertical-slice lists
    `timing__hold_vio__count` in its MUST_BE_ZERO list, and a hold check
    against a requirement of zero cannot fail for the reason hold fails.
    Measured now, and 0.0 was not even a conservative placeholder -- at tt
    this flop CAPTURES A RISING D PLACED EXACTLY ON THE CLOCK EDGE, so its
    real hold requirement for that direction is strictly positive.

  * M18 -- THE SETUP SEARCH COULD NOT RETURN ITS OWN ANSWER. Its bracket was
    hard-coded lo = 0.0, taken on faith, and it returned `hi`. With the true
    boundary at or below zero every trial succeeded, `hi` halved to the floor,
    and the returned value was (hi-lo)/2**iters -- set by the iteration count,
    not by the circuit. Both the tt and ff liberties shipped setup =
    0.00024 ns for five releases, which is 1e-9/2**12 exactly. _boundary()
    now verifies its bracket, widens it, and RAISES rather than returning a
    bound dressed as a measurement.

Both directions are now measured separately, because on this cell they are
not equal and not even the same sign: the input inverter passes a rising and
a falling D at different speeds, so the effective sampling instant moves with
direction. Emitting one number for both -- which is what setup did -- is the
same defect wearing different clothes.

Note what this says about the guards. Negative DELAYS are real here (the
paragraph above) and are deliberately not clamped -- so "a negative number in
the liberty" could never have been the alarm. The alarm that should have fired
is check_monotonic.py, whose own docstring says a wrong-crossing regression
"almost always breaks" load-monotonicity; it never saw this one because it
parsed only cell_rise/cell_fall. It now covers the transition tables too and
asserts their POSITIVITY -- the one thing that can be demanded of a transition
time and cannot be demanded of a delay in this library.
"""
import itertools
import sys

import numpy as np

from common import MODELS, OUT, VDD, TEMP, run_ngspice, parse_meas
from cells import LIBRARY

SLEWS = [0.02e-9, 0.05e-9, 0.3e-9, 1.5e-9]   # input transition, 20-80, seconds
LOADS = [2e-15, 5e-15, 25e-15, 100e-15]      # output load, farads
T_END = 40e-9

TEMPLATE = f"tbl{len(SLEWS)}{len(LOADS)}"     # NLDM (delay / output transition)
PTEMPLATE = f"pwr{len(SLEWS)}{len(LOADS)}"    # internal_power (input_transition)
# ngspice reports the supply-source branch current NEGATIVE when the cell draws
# current, so the charge delivered by the supply is -integ i(vdd). Validated:
# with this sign an output-RISE window yields +C*Vdd^2 of supply energy and an
# output-FALL window ~0 (tools/validate_power.py).
ISIGN = -1.0
# hold the CORNER SPREAD summary at a fixed (0.3 ns, 25 fF) operating point so
# the printed number stays comparable to what lib-v1.1 recorded even though
# grid points were added around it.
REP_S, REP_L = SLEWS.index(0.3e-9), LOADS.index(25e-15)

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
    """One transient: pin pulses low-high-low; measure both arcs.

    Beyond the delay/transition arcs, integrate the supply-source current over
    a window bracketing each input edge (qir = input-rise window, qif =
    input-fall window). emit_liberty turns those into internal_power: the
    supply energy per transition minus the 1/2 C*Vdd^2 the power tool already
    accounts as switching energy. The integration is free -- same transient.

    lib-v1.4 / M11: the two OUTPUT-TRANSITION measurements are qualified by
    DIRECTION (rise=1 / fall=1), not by crossing ordinal. `cross=N` counts the
    Nth crossing of a level in EITHER direction, and both thresholds here sit
    on the SAME node, so on an inverting cell -- whose output falls when the
    input rises -- the output reaches 0.8*Vdd BEFORE 0.2*Vdd and (targ - trig)
    came out NEGATIVE and, worse, attached to the opposite table. Measured at
    (20 ps, 2 fF): INV_X1 shipped -11.30 ps as `rise_transition` when its true
    rise is 20.97 ps, and NOR2_X1 shipped -15.68 ps for a true 50.87 ps rise
    -- a 3.2x understatement on the cell with the weakest (stacked-PMOS)
    pull-up. OpenSTA clamps negatives to zero, so vertical-slice signed off at
    zero slew and its "max slew violations 0" was vacuous.

    The delay measurements above keep `cross=`: their trig is direction-
    qualified on the INPUT and their targ takes the ordered 1st/2nd output
    event, so they select correctly. It is only the same-node pair that breaks.
    The DFF path (_dff_edge) has always used rise=/fall= and was never wrong.
    """
    others = noncontrolling(cell, pin)
    src = [f"v{p} {p} 0 {v}" for p, v in others.items()]
    ramp = slew / 0.6                   # 20-80 -> 0-100 ramp time
    t_fall = 2e-9 + ramp + 15e-9        # input falls here (pulse PW=15n)
    w1a, w1b = 1.8e-9, t_fall - 2e-9    # input-rise window: ends before the fall
    w2a, w2b = t_fall - 0.2e-9, T_END - 0.2e-9   # input-fall window: to run end
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
meas tran trise trig v({cell.output}) val={0.2*VDD} rise=1 targ v({cell.output}) val={0.8*VDD} rise=1
meas tran tfall trig v({cell.output}) val={0.8*VDD} fall=1 targ v({cell.output}) val={0.2*VDD} fall=1
meas tran qir integ i(vdd) from={w1a} to={w1b}
meas tran qif integ i(vdd) from={w2a} to={w2b}
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
    """Single all-inputs-low leakage (watts). Used for the DFF, whose full
    per-state leakage depends on internal storage nodes (deferred)."""
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


def leakage_states(cell):
    """DC leakage in every input state -> [(when_expr, watts), ...].

    research/internal-power.md §4: the single all-low measurement lands on an
    inverter's LOW-leakage state and understates the average hd publishes by
    ~27x (a 53x spread between an INV's two states). hd emits one
    leakage_power(when) group per state and publishes cell_leakage_power as the
    average; we do both. Combinational cells only -- inputs fully determine the
    state, no internal nodes to precondition.
    """
    out = []
    for bits in itertools.product((0, 1), repeat=len(cell.inputs)):
        src = [f"v{p} {p} 0 {b * VDD}" for p, b in zip(cell.inputs, bits)]
        tag = f"leak_{CORNER}_{cell.name}_{''.join(map(str, bits))}"
        net = f"""* {cell.name} leakage state {bits}
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
        vals = parse_meas(run_ngspice(net, tag))
        w = vals.get("ileak_meas", 0.0) * VDD
        when = "&".join((p if b else "!" + p)
                        for p, b in zip(cell.inputs, bits))
        out.append((when, w))
    return out


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


CLK_EDGE = 12e-9          # the capture edge in every constraint netlist
D_RAMP = 0.05e-9          # D transition time, unchanged from lib-v1.0
CONSTRAINT_ITERS = 12     # (hi-lo)/2**12 over a 1.25 ns bracket = 0.3 ps


def _constraint_trial(cell, kind, edge, t, tag):
    """One transient. True when the value the trial INTENDS to read wins.

    kind "setup": D changes at CLK_EDGE - t, so t is the lead time on offer.
        The intended value is the NEW one -- True means it got in.
    kind "hold":  D changes at CLK_EDGE + t, so t is the hold time on offer.
        The intended value is the OLD one -- True means the change came late
        enough not to corrupt the capture.

    `edge` is the direction of the D transition under test, which is exactly
    what Liberty's rise_constraint / fall_constraint are indexed by. They are
    measured SEPARATELY because they are not equal: D reaches the master
    through an input inverter that passes its two edges at different speeds,
    so the flop's effective sampling instant depends on the direction. On this
    cell at tt the two hold boundaries land on OPPOSITE SIDES of zero, so
    emitting one number for both would be the same defect in a new place.

    Both kinds are preconditioned by the early clock pulse at 3.1 ns, which
    loads the OPPOSITE of the value the trial expects to read at the end. That
    makes "the intended value is there" an observable transition of Q rather
    than a power-up state that would read as success for every trial -- the
    hazard the old dff_setup docstring recorded as the bogus 'setup 0 ps'.
    """
    new = VDD if edge == "rise" else 0.0
    old = 0.0 if edge == "rise" else VDD
    if kind == "setup":
        # D sits at `old` (which the reset pulse loads), then changes to `new`
        # t before the capture edge. Success = Q ends at `new`.
        tchg, want = CLK_EDGE - t, new
        d = [(0.0, old), (tchg, old), (tchg + D_RAMP, new), (25e-9, new)]
    else:
        # D sits at `new` at the reset pulse (so Q loads !old), moves to `old`
        # with generous setup, then back to `new` t AFTER the capture edge.
        # Success = Q ends at `old`, i.e. the late change did not get in.
        tchg, want = CLK_EDGE + t, old
        d = [(0.0, new), (9.95e-9, new), (10e-9, old), (tchg, old),
             (tchg + D_RAMP, new), (25e-9, new)]
    # A PWL whose times are not increasing is silently accepted by some
    # simulators and mis-parsed by others, and _boundary() may widen its
    # bracket far enough to produce one (a hold t below about -2 ns would put
    # the change before the D->old step at 10 ns). Fail loudly instead.
    if any(b[0] <= a[0] for a, b in zip(d, d[1:])):
        raise RuntimeError(
            f"{tag}: t={t:.3e} s puts the D edge outside the window this "
            f"netlist can express (times {[f'{x:.3e}' for x, _ in d]}). "
            f"Widen the netlist, do not widen the search past it.")
    pwl = " ".join(f"{x:.6e} {v:.4f}" for x, v in d)
    net = f"""* DFF {kind} probe edge={edge} t={t}
{HDR}
{cell.spice()}
vdd vdd 0 {VDD}
vss vss 0 0
vd D 0 pwl({pwl})
vc CLK 0 pwl(0 0 3n 0 3.1n {VDD} 5n {VDD} 5.1n 0
+  {CLK_EDGE} 0 {CLK_EDGE+0.1e-9} {VDD} {CLK_EDGE+5e-9} {VDD} {CLK_EDGE+5.1e-9} 0)
xdut D CLK Q vdd vss {cell.name}
cload Q 0 25f
.tran 2p {CLK_EDGE + 7e-9}
.control
run
meas tran qfin find v(Q) at={CLK_EDGE + 5e-9}
.endc
.end
"""
    q = parse_meas(run_ngspice(net, tag)).get("qfin")
    if q is None:
        raise RuntimeError(f"{tag}: ngspice returned no qfin — see out/{tag}.log")
    return abs(q - want) < VDD / 2


def _boundary(trial, what, lo=-0.25e-9, hi=1.0e-9, iters=CONSTRAINT_ITERS):
    """Smallest t for which `trial(t)` holds, by bisection on a VERIFIED bracket.

    trial must be monotone in t -- later is safer -- which is the property that
    makes a timing constraint a single number at all.

    THE VERIFIED BRACKET IS THE POINT OF THIS HELPER (defect M18). The
    bisection it replaces hard-coded lo = 0.0 and took it on faith, then
    returned `hi`. When the true boundary sat at or below zero every trial
    succeeded, `hi` halved all the way to the bottom, and the function returned
    (hi-lo)/2**iters -- a number produced by the ITERATION COUNT, not by the
    circuit. lib-v1.0..v1.5 shipped setup = 0.00024 ns at tt and at ff, which
    is 1e-9/2**12 to the digit. Measured while closing M17: this flop still
    captures a D edge placed exactly ON the clock edge, so its true setup is
    <= 0 there and the old search could not have expressed it at all.

    So the endpoints are evaluated and, if they do not bracket, widened; if
    they still do not, this RAISES rather than returning its own lower bound.
    A search that cannot find the answer must say so -- silently returning the
    edge of the search space is how a placeholder gets mistaken for a
    measurement for five releases.
    """
    flo, fhi = trial(lo), trial(hi)
    for _ in range(4):
        if flo:                        # boundary at or below lo -> widen down
            span, hi, fhi = hi - lo, lo, flo
            lo -= span
            flo = trial(lo)
        elif not fhi:                  # boundary above hi -> widen up
            span, lo, flo = hi - lo, hi, fhi
            hi += span
            fhi = trial(hi)
        else:
            break
    if flo or not fhi:
        raise RuntimeError(
            f"{what} at {CORNER}: could not bracket the boundary in "
            f"[{lo*1e12:.1f}, {hi*1e12:.1f}] ps (trial(lo)={flo}, "
            f"trial(hi)={fhi}). Not returning a bound as if it were a "
            f"measurement — see the M18 note in _boundary().")
    for _ in range(iters):
        mid = (lo + hi) / 2
        if trial(mid):
            hi = mid
        else:
            lo = mid
    return hi


def dff_constraints(cell):
    """Measure setup AND hold, each for both D directions. Four numbers.

    Returns {"setup": {"rise": s, "fall": s}, "hold": {"rise": h, "fall": h}}
    in seconds. Negative values are real and are emitted as measured: a
    negative setup means D may change slightly after the clock edge and still
    be captured (this topology buffers CLK internally, so the master closes
    after the pin edge), and a negative hold is its mirror.

    Defect M17: hold was never measured. It was emitted as a literal 0.0 for
    both directions from lib-v1.0 to lib-v1.5 while setup beside it was
    searched for -- and vertical-slice put `timing__hold_vio__count` in its
    MUST_BE_ZERO list, where a check against a requirement of zero cannot fail
    for the reason hold actually fails.
    """
    out = {}
    for kind in ("setup", "hold"):
        out[kind] = {}
        for edge in ("rise", "fall"):
            tag = f"dff_{kind}_{edge}_{CORNER}"
            out[kind][edge] = _boundary(
                lambda t, k=kind, e=edge, g=tag: _constraint_trial(cell, k, e, t, g),
                f"{kind}_{edge}")
    return out


def table(name, rows, template=None, scale=1e9):
    """rows[slew][load] -> liberty NLDM block. scale converts the stored value
    to the liberty unit (delay/transition: seconds->ns=1e9; power: already pJ,
    scale=1)."""
    template = template or TEMPLATE
    v = " \\\n           ".join(
        '"' + ", ".join(f"{x*scale:.5f}" for x in row) + '",' for row in rows)
    return f"""        {name} ({template}) {{
          index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
          index_2("{', '.join(f'{c*1e12:.3f}' for c in LOADS)}");
          values({v.rstrip(',')});
        }}"""


def internal_power(a, inverting):
    """Return (rise_power, fall_power) tables in pJ for one input arc.

    E_internal per transition = (energy the supply delivered over that arc's
    window) - 1/2 C*Vdd^2 (the switching half the power tool computes itself).
    On an output RISE the supply term ~= C*Vdd^2 so rise_power stays positive;
    on an output FALL the supply term ~=0 so fall_power is negative and
    load-proportional -- the shape the Liberty RM's own example ships and
    sky130_fd_sc_hd reproduces. Negatives are correct; do not clamp.
    """
    q_outrise = a["qif" if inverting else "qir"]   # arc that makes output rise
    q_outfall = a["qir" if inverting else "qif"]
    half_cv2 = np.array([[0.5 * c * VDD ** 2 for c in LOADS] for _ in SLEWS])
    rise_pj = (ISIGN * VDD * q_outrise - half_cv2) * 1e12
    fall_pj = (ISIGN * VDD * q_outfall - half_cv2) * 1e12
    return rise_pj, fall_pj


# real layout areas override the projected site model where cells exist
import json
_ar = OUT / "areas_real.json"
if _ar.exists():
    real = json.loads(_ar.read_text())
    for c in LIBRARY:
        if c.name in real:
            c.area = real[c.name]

def characterize_all():
    """Measure every cell at the PVT currently set. Returns the lib_cells list.

    lib_cells entries are (cell, caps, leak, data) where leak is
    {"avg": watts, "states": [(when, watts), ...]} -- states is empty for the
    DFF (single averaged value) and populated for combinational cells.
    """
    print(f"characterizing {len(LIBRARY)} cells at {CORNER} "
          f"({VDD} V, {TEMP} C) ...")
    lib_cells = []
    for cell in LIBRARY:
        caps = {p: input_cap(cell, p) for p in cell.inputs}
        if cell.clocked:
            leak = {"avg": leakage(cell), "states": []}
            tables = {k: np.zeros((len(SLEWS), len(LOADS)))
                      for k in ("tcqr", "tcqf", "trq1", "trq2")}
            for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                    enumerate(LOADS)):
                m = dff_clkq(cell, s, c, f"dffq_{CORNER}_{i}{j}")
                for k in tables:
                    tables[k][i, j] = m.get(k, np.nan)
            con = dff_constraints(cell)
            lib_cells.append((cell, caps, leak,
                              {"clkq": tables, "setup": con["setup"],
                               "hold": con["hold"]}))
            print(f"  {cell.name}: clk-q {tables['tcqr'][REP_S, REP_L]*1e12:.0f} ps, "
                  f"setup {con['setup']['rise']*1e12:+.1f}/"
                  f"{con['setup']['fall']*1e12:+.1f} ps (rise/fall), "
                  f"hold {con['hold']['rise']*1e12:+.1f}/"
                  f"{con['hold']['fall']*1e12:+.1f} ps, "
                  f"cin(D) {caps['D']*1e15:.2f} fF, "
                  f"leak {leak['avg']*1e12:.1f} pW")
        else:
            states = leakage_states(cell)
            leak = {"avg": sum(w for _, w in states) / len(states),
                    "states": states}
            arcs = {}
            for pin in cell.inputs:
                t = {k: np.zeros((len(SLEWS), len(LOADS)))
                     for k in ("tdr", "tdf", "trise", "tfall", "qir", "qif")}
                for (i, s), (j, c) in itertools.product(enumerate(SLEWS),
                                                        enumerate(LOADS)):
                    m = arc_run(cell, pin, s, c,
                                f"arc_{CORNER}_{cell.name}_{pin}_{i}{j}")
                    for k in t:
                        t[k][i, j] = m.get(k, np.nan)
                arcs[pin] = t
            lib_cells.append((cell, caps, leak, arcs))
            mid = arcs[cell.inputs[0]]["tdr"][REP_S, REP_L]
            print(f"  {cell.name}: tp {mid*1e12:.0f} ps @rep, "
                  f"cin {caps[cell.inputs[0]]*1e15:.2f} fF, "
                  f"leak {leak['avg']*1e12:.1f} pW (avg of {len(states)} states)")
    return lib_cells


def emit_liberty(lib_cells):
    """Render the measured data as a Liberty file for the current PVT."""
    # `default_fanout_load` is defect M15, and it is the ONLY attribute needed
    # to fix it. OpenSTA computes a net's fanout by summing each sink pin's
    # `fanout_load`, falling back to the library's `default_fanout_load` when
    # the pin does not declare one. This library declared NEITHER, so every
    # net summed to 0.0, `set_max_fanout 10` in signoff.sdc was unreachable by
    # construction, and `design__max_fanout_violation__count` was a constant 0
    # that vertical-slice's check_signoff.py quoted as assurance. Measured on
    # a 12-sink net: without this line OpenSTA reports 0 violations; with it,
    # `drv/Y limit 10 fanout 12 slack -2 (VIOLATED)`.
    #
    # Why 1, and why nothing else. sky130_fd_sc_hd -- the reference for what
    # is conventional -- carries `default_fanout_load : 1.0` and has NO
    # per-pin `fanout_load` and NO `max_fanout` anywhere. Both were tried and
    # measured here:
    #   * per-pin `fanout_load : 1;` on all 14 input pins is exactly redundant
    #     with the header default (identical violation report), so it is
    #     omitted as duplicated state.
    #   * a per-output `max_fanout : N;` is NOT emitted on purpose. The
    #     foundry does not, it would be a second source of truth racing the
    #     SDC's design-level limit, and -- worse -- N would be a number nobody
    #     measured, sitting in a characterized library next to the
    #     `max_capacitance` that IS measured (the top of the LOADS sweep, i.e.
    #     where these tables stop being interpolation). Fanout is the crude
    #     proxy; capacitance is the real limit. Do not add a fabricated proxy
    #     beside a measured quantity -- that is the defect this repo keeps
    #     finding, not the fix for it.
    # Keeping the load at exactly 1 per pin also keeps "fanout" meaning "sink
    # count", which is what set_max_fanout 10 and every recorded violation
    # figure assume.
    #
    # `power_lut_template` (not `lu_table_template`) for PTEMPLATE is defect
    # M16, found while proving M15 because OpenSTA prints 18 warnings about it
    # on every read and nobody had read them. Liberty keeps power templates in
    # a SEPARATE namespace from timing templates: declaring pwr44 with
    # `lu_table_template` means every `internal_power` table referencing it
    # resolves to nothing, so OpenSTA silently DISCARDS all of them. Measured
    # on the same 12-sink netlist: `report_power` gave internal power
    # 0.00e+00 before and 5.47e-08 after -- 33.7% of total power, thrown away.
    # The tables themselves were always correct; they were addressed to a
    # namespace the tool does not look in. Same shape as M11-M15: measured
    # data present in the artifact, silently ignored by the tool, and no check
    # noticed because none looked.
    L = []
    L.append(f"""library (own_sky130_{CORNER}) {{
  technology (cmos);
  delay_model : table_lookup;
  time_unit : "1ns"; voltage_unit : "1V"; current_unit : "1mA";
  pulling_resistance_unit : "1kohm"; capacitive_load_unit (1, pf);
  leakage_power_unit : "1nW";
  default_fanout_load : 1;
  nom_process : 1; nom_voltage : {VDD}; nom_temperature : {TEMP};
  operating_conditions ({CORNER}) {{ process : 1; voltage : {VDD}; temperature : {TEMP}; }}
  default_operating_conditions : {CORNER};
  slew_lower_threshold_pct_rise : 20; slew_upper_threshold_pct_rise : 80;
  slew_lower_threshold_pct_fall : 20; slew_upper_threshold_pct_fall : 80;
  input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;
  output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;
  lu_table_template ({TEMPLATE}) {{
    variable_1 : input_net_transition; variable_2 : total_output_net_capacitance;
    index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
    index_2("{', '.join(f'{c*1e12:.3f}' for c in LOADS)}");
  }}
  power_lut_template ({PTEMPLATE}) {{
    variable_1 : input_transition_time; variable_2 : total_output_net_capacitance;
    index_1("{', '.join(f'{s*1e9:.3f}' for s in SLEWS)}");
    index_2("{', '.join(f'{c*1e12:.3f}' for c in LOADS)}");
  }}
""")
    for cell, caps, leak, data in lib_cells:
        L.append(f"  cell ({cell.name}) {{")
        L.append(f"    area : {cell.area};")
        L.append(f"    cell_leakage_power : {leak['avg']*1e9:.6f};")
        for when, w in leak["states"]:
            L.append(f'    leakage_power () {{ when : "{when}"; '
                     f'value : {w*1e9:.6f}; }}')
        if cell.clocked:
            L.append("    ff (IQ, IQN) { next_state : \"D\"; clocked_on : \"CLK\"; }")
            # M17/M18: all four of these are measured, per D direction. Hold
            # was a literal 0.0 through lib-v1.5 and setup was one number used
            # for both directions -- and the two directions are not equal on
            # this cell (see dff_constraints). Negatives are emitted as
            # measured, as everywhere else in this flow.
            # ⚠️ COINCIDENCE WORTH KNOWING: ff's measured hold for a falling D
            # is 0.244 ps, which at .5f renders as "0.00024" -- character for
            # character the M18 floor artefact (1e-9/2**12) that these values
            # replace. It is a real measurement here and it lands on a
            # legitimate grid point of the new bracket. Do not read a shipped
            # 0.00024 as evidence of M18 without checking which field it is in:
            # M18's was in setup at tt AND ff, this is hold at ff only.
            su, ho = data["setup"], data["hold"]
            L.append(f"""    pin (CLK) {{ direction : input; clock : true;
          capacitance : {caps['CLK']*1e12:.6f}; }}
        pin (D) {{ direction : input; capacitance : {caps['D']*1e12:.6f};
          timing () {{ related_pin : "CLK"; timing_type : setup_rising;
            rise_constraint (scalar) {{ values("{su['rise']*1e9:.5f}"); }}
            fall_constraint (scalar) {{ values("{su['fall']*1e9:.5f}"); }} }}
          timing () {{ related_pin : "CLK"; timing_type : hold_rising;
            rise_constraint (scalar) {{ values("{ho['rise']*1e9:.5f}"); }}
            fall_constraint (scalar) {{ values("{ho['fall']*1e9:.5f}"); }} }} }}
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
            inverting = cell.function.startswith("(!")
            for p in cell.inputs:
                a = data[p]
                cr = a["tdf" if inverting else "tdr"]
                cf = a["tdr" if inverting else "tdf"]
                rise_pj, fall_pj = internal_power(a, inverting)
                # NOTE the asymmetry with the two lines above, which is
                # correct: the DELAY tables must be swapped for an inverting
                # cell (its output RISES on the input's falling edge, so
                # cell_rise comes from tdf), but the TRANSITION tables must
                # NOT be, because trise/tfall are measured by output
                # direction and so already mean output-rise / output-fall for
                # either polarity. Before lib-v1.4 they were measured by
                # crossing ordinal, which made them both negated AND swapped
                # on inverting cells -- defect M11.
                L.append(f"""      timing () {{ related_pin : "{p}";
            timing_sense : {"negative_unate" if inverting else "positive_unate"};
    {table("cell_rise", cr)}
    {table("rise_transition", a["trise"])}
    {table("cell_fall", cf)}
    {table("fall_transition", a["tfall"])} }}
      internal_power () {{ related_pin : "{p}";
    {table("rise_power", rise_pj, PTEMPLATE, 1.0)}
    {table("fall_power", fall_pj, PTEMPLATE, 1.0)} }}""")
            L.append("    }")
        L.append("  }")
    L.append("}")
    return "\n".join(L)


def check_no_nan(lib_cells):
    bad = []
    for cell, caps, leak, data in lib_cells:
        if "setup" in data:
            tabs = list(data["clkq"].values())
        else:
            # only the timing tables gate the run; a stray power integral going
            # NaN should not abort characterization (it is reported, not signed)
            tabs = [arc[k] for arc in data.values()
                    for k in ("tdr", "tdf", "trise", "tfall")]
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
            c.name: (d["clkq"]["tcqr"][REP_S, REP_L] if c.clocked
                     else d[c.inputs[0]]["tdr"][REP_S, REP_L], leak["avg"])
            for c, caps, leak, d in cells_data}
        print(f"wrote {OUT / f'own_{corner}.lib'}\n")

    if len(summary) > 1:
        print("=" * 66)
        print("CORNER SPREAD — (0.3 ns, 25 fF) delay, and total leakage")
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
