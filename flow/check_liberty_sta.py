"""lib-v1.5: assert that the tool can actually SEE what the liberty declares.

WHY THIS FILE EXISTS (defects M15 and M16)
------------------------------------------
Both were the same failure and neither was a wrong number. The measured data
was correct and present in the file; it was addressed so that OpenSTA never
looked at it, and every downstream check therefore reported a comfortable
constant.

  * M15 — the library declared no `fanout_load` and no `default_fanout_load`.
    OpenSTA computes a net's fanout by summing `fanout_load` over its sinks,
    so every net in every design summed to 0.0, `set_max_fanout 10` could not
    be exceeded by any circuit, and `design__max_fanout_violation__count` was
    a constant 0. vertical-slice had that metric in its MUST_BE_ZERO list and
    quoted it as assurance. Measured on the shipped routed netlist: 0
    violations before, 22 after (worst `wire82/Y`, fanout 29 against 10).

  * M16 — the power tables were declared with `lu_table_template` instead of
    `power_lut_template`. Liberty keeps power templates in a SEPARATE
    namespace, so every `internal_power` table resolved to nothing and
    OpenSTA discarded all of them. It printed 18 warnings on every single
    read for four library releases and nobody read them. Measured: reported
    internal power 0.00e+00 before, 5.47e-08 after — a third of total power.

  * M17 [lib-v1.6] — the DFF hold constraint was the literal `0.0`, never
    measured, for five releases. Same family, one step further out: with M15
    the tool could not see a limit that was absent; here the tool could see
    the number perfectly well and the number was a placeholder. The check it
    fed — `timing__hold_vio__count` in vertical-slice's MUST_BE_ZERO list —
    therefore could not fail for the reason hold actually fails.

    The guard for it cannot be "assert the value is non-zero": a hold
    constraint is legitimately allowed to be zero or negative, so that test
    would be a spelling test with a false-failure mode. What can be demanded
    is that the number MOVES SIGNOFF. So check_hold() runs the same design
    twice — once with the liberty as shipped, once with its hold constraints
    forced back to 0.0 — and asserts the worst hold slack differs by exactly
    the constraint. If the library ships a placeholder the two runs are
    identical and the delta is 0, which is the failure. Measured on lib-v1.5
    (the pre-fix library) the delta was exactly 0.000 ns; on lib-v1.6 it is
    the emitted hold time.

    OpenSTA states the defect itself, if anyone runs the report. On lib-v1.5
    `report_checks -path_delay min` over this probe prints, in the required-
    time column of the launch->cap hold check:

        0.00    0.00   clock reconvergence pessimism
                0.00 ^ cap/CLK (DFF_X1)
        0.00    0.00   library hold time          <-- M17, in the tool's words
                0.00   data required time

    which is why the guard is worth having: nothing was hidden, and the
    number sat there for five releases behind a green metric.

THE POINT, AND WHY THIS IS NOT check_monotonic.py
-------------------------------------------------
check_monotonic.py reads the liberty and checks its NUMBERS. It could never
have caught either defect, because both numbers were right. What was wrong
was whether the tool consuming the file could reach them — a property of the
liberty PLUS the tool together, which is only observable by running the tool.
So this guard runs OpenSTA and checks behaviour, not spelling. Asserting that
`default_fanout_load` appears in the text would be one more proxy, and a
proxy standing in for the property is the defect, not the fix.

It also asserts the check can PASS, not just fail. A guard wedged at
"violation" is exactly as useless as one wedged at "clean" — it just fails in
the other direction — so a 9-sink net must come back clean in the same run
that a 12-sink net comes back violated.

Usage
-----
    python3 flow/check_liberty_sta.py            # every corner hardening lib
    python3 flow/check_liberty_sta.py out/x.lib  # one file

OpenSTA is found as `sta` on PATH, else run from the librelane image via
docker (which is how CI has it, and the only way it exists on the Windows
box — there, run this script from inside WSL).
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
WORK = OUT / "sta_check"
IMAGE = os.environ.get("LIBRELANE_IMAGE", "ghcr.io/librelane/librelane:3.0.5")

# The design under test: one driver over the limit, one driver under it. Both
# in the same netlist so a single STA run proves the check can fail AND pass.
LIMIT = 10
OVER, UNDER = 12, 9

# Any table whose template does not resolve is silently dropped by OpenSTA and
# announced only in a warning. That is M16's exact signature, so the warning is
# promoted to a failure rather than left for someone to notice.
TEMPLATE_WARN = re.compile(r"table template (\S+) not found", re.I)


def netlist():
    sinks = [f"INV_X1 over{i} (.A(n_over), .Y(o_over{i}));" for i in range(OVER)]
    sinks += [f"INV_X1 under{i} (.A(n_under), .Y(o_under{i}));" for i in range(UNDER)]
    ports = ([f"o_over{i}" for i in range(OVER)] +
             [f"o_under{i}" for i in range(UNDER)])
    return (f"module fanout_probe (a, b, {', '.join(ports)});\n"
            f"  input a, b;\n"
            f"  output {', '.join(ports)};\n"
            f"  wire n_over, n_under;\n"
            f"  INV_X1 drv_over (.A(a), .Y(n_over));\n"
            f"  INV_X1 drv_under (.A(b), .Y(n_under));\n  " +
            "\n  ".join(sinks) + "\nendmodule\n")


SDC = f"""set_max_fanout {LIMIT}.0000 [current_design]
set_input_transition 0.05 [all_inputs]
"""

TCL = """read_liberty own.lib
read_verilog fanout_probe.v
link_design fanout_probe
read_sdc fanout_probe.sdc
puts "@@@FANOUT [sta::max_fanout_violation_count]"
report_check_types -max_fanout -violators
puts "@@@POWER_START"
report_power
"""


def run_sta(script="probe.tcl"):
    if shutil.which("sta"):
        cmd = ["sta", "-no_init", "-exit", script]
    elif shutil.which("docker"):
        cmd = ["docker", "run", "--rm", "-v", f"{WORK}:/w", "-w", "/w",
               IMAGE, "sta", "-no_init", "-exit", script]
    else:
        sys.exit("FAIL: neither `sta` nor `docker` on PATH — cannot run this "
                 "guard. On the Windows box, run it from inside WSL.")
    cp = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True)
    return cp.stdout + cp.stderr


# ---------------------------------------------------------------- M17 (hold)

# Two flops, clock to clock, with the shortest data path a netlist can have.
# The hold check at `cap` is then clk->Q plus a wire against the DFF's hold
# requirement, which is the arc under test and nothing else.
HOLD_V = """module hold_probe (clk, d, q);
  input clk, d;
  output q;
  wire mid;
  DFF_X1 launch (.D(d), .CLK(clk), .Q(mid));
  DFF_X1 cap (.D(mid), .CLK(clk), .Q(q));
endmodule
"""

# The input delay is half a period so the port->launch/D hold check cannot be
# the worst one: the launch->cap path must be what sets the reported min slack,
# or the delta below would be measuring some other arc's constraint.
HOLD_SDC = """create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay -clock clk 5.0 [get_ports d]
set_input_transition 0.05 [all_inputs]
"""

# -digits 5 on BOTH reports. `report_worst_slack -min` defaults to 2 decimal
# places in ns, i.e. 10 ps granularity, which is coarser than the constraint
# being measured -- the first draft of this guard quantised a 6.65 ps delta to
# exactly 10.000 ps and then failed the library for it.
HOLD_TCL = """read_liberty {lib}
read_verilog hold_probe.v
link_design hold_probe
read_sdc hold_probe.sdc
report_worst_slack -min -digits 5
report_checks -path_delay min -digits 5
"""

WORST_MIN = re.compile(r"worst slack\s+min\s+(-?[\d.]+)", re.I)
# The tool's own statement of the constraint it applied on the reported path.
LIB_HOLD = re.compile(r"^\s*(-?[\d.]+)\s+(-?[\d.]+)\s+library hold time\s*$",
                      re.M)

# The emitted hold group, both directions, captured so they can be forced to
# zero. Matching this shape also asserts the group exists at all -- a liberty
# with no hold_rising arc would otherwise sail through every check here.
HOLD_GROUP = re.compile(
    r'(timing_type\s*:\s*hold_rising;\s*'
    r'rise_constraint\s*\(scalar\)\s*\{\s*values\()"([^"]*)"(\);\s*\}\s*'
    r'fall_constraint\s*\(scalar\)\s*\{\s*values\()"([^"]*)"(\))', re.S)


def check_hold(lib):
    """Assert the hold constraint reaches OpenSTA and moves hold slack by itself.

    Runs the same two-flop design twice, changing exactly one thing: the hold
    constraint in the liberty. See the M17 note in the module docstring for why
    "is it non-zero" would be the wrong test.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    text = lib.read_text()
    m = HOLD_GROUP.search(text)
    if not m:
        return [f"{lib.name}: no `hold_rising` constraint group found at all. "
                f"Every sequential cell needs one; without it OpenSTA has no "
                f"hold requirement to check and `timing__hold_vio__count` is "
                f"meaningless."]
    declared = (float(m.group(2)), float(m.group(4)))       # rise, fall (ns)

    # DO NOT predict which of the two arcs OpenSTA will report. The worst min
    # path is the one with the smallest (arrival - required), and the arrival
    # differs by direction too -- launch/Q's falling edge is not as fast as its
    # rising one. Measured while writing this: with rise +6.65 ps and fall
    # -5.55 ps declared, OpenSTA reported the FALL arc, because that path's
    # arrival is smaller by more than the 12 ps between the two requirements.
    # So the guard reads back the constraint the tool says it used, and checks
    # the file against THAT.
    # Three runs, because a two-run delta is not arc-independent. Measured at
    # ff, where the shipped values are rise +12.15 ps and fall +0.24 ps:
    # zeroing BOTH made the fall path (whose arrival is 6.7 ps earlier) the
    # worst one instead of the rise path, so the change in worst slack was
    # 5.48 ps and matched neither constraint. Nothing was wrong with the
    # library — the binding arc had moved out from under the comparison.
    #
    # So reachability is proved with a SYNTHETIC constraint instead: force both
    # directions to zero, then both to PROBE ns. A single value on both arcs
    # cannot switch which one binds, so the worst slack must move by exactly
    # PROBE. The shipped numbers are checked separately, against the value
    # OpenSTA reports having applied.
    PROBE = 1.0
    slacks, used = {}, {}
    variants = (
        ("real", text),
        ("zeroed", HOLD_GROUP.sub(
            lambda x: f'{x.group(1)}"0.0"{x.group(3)}"0.0"{x.group(5)}', text)),
        ("probe", HOLD_GROUP.sub(
            lambda x: f'{x.group(1)}"{PROBE}"{x.group(3)}"{PROBE}"{x.group(5)}',
            text)),
    )
    for label, body in variants:
        (WORK / f"hold_{label}.lib").write_text(body)
        (WORK / "hold_probe.v").write_text(HOLD_V)
        (WORK / "hold_probe.sdc").write_text(HOLD_SDC)
        (WORK / f"hold_{label}.tcl").write_text(
            HOLD_TCL.format(lib=f"hold_{label}.lib"))
        log = run_sta(f"hold_{label}.tcl")
        hit = WORST_MIN.search(log)
        if not hit:
            print(log[-3000:])
            return [f"{lib.name}: OpenSTA reported no min-path slack for the "
                    f"two-flop probe ({label} run) — cannot tell whether the "
                    f"hold constraint is used."]
        slacks[label] = float(hit.group(1))
        h = LIB_HOLD.search(log)
        if not h:
            return [f"{lib.name}: the min-path report carries no `library hold "
                    f"time` row ({label} run), so OpenSTA applied no hold "
                    f"requirement to a flop-to-flop path at all."]
        used[label] = float(h.group(2))

    # 1. The file and the tool must agree: whichever arc OpenSTA reported, the
    #    requirement it applied has to be one of the two the liberty declares.
    if not any(abs(used["real"] - d) < 1e-9 for d in declared):
        return [f"{lib.name}: OpenSTA applied a hold requirement of "
                f"{used['real']*1000:+.3f} ps, which is neither of the values "
                f"the liberty declares ({declared[0]*1000:+.3f} / "
                f"{declared[1]*1000:+.3f} ps). The number in the file is not "
                f"the number being checked against."]

    # 2. The field must be REACHED and must move signoff proportionally. Both
    #    directions carry the same value in these two runs, so the binding arc
    #    cannot change between them and the shift must be exactly PROBE.
    shift = slacks["zeroed"] - slacks["probe"]
    if abs(shift - PROBE) > 5e-4:
        return [f"{lib.name}: moving the hold constraint from 0 to {PROBE} ns "
                f"shifted worst hold slack by {shift:.5f} ns, not {PROBE}. "
                f"OpenSTA is not consuming the hold constraint in this liberty, "
                f"so any hold verdict computed from it means nothing."]

    # 3. M17 itself: a requirement of zero cannot be violated for the reason
    #    hold is violated. Note this fires on what the TOOL used, not on the
    #    text — and only when BOTH declared directions are zero, so a
    #    legitimately-zero single arc is not condemned.
    if used["real"] == 0.0 and all(d == 0.0 for d in declared):
        return [f"{lib.name}: every hold constraint on this flop is 0.0, and "
                f"OpenSTA duly applied 0.00000 ns on the worst min path — so "
                f"hold is being signed off against a requirement that cannot "
                f"be violated for the reason hold is violated. This is defect "
                f"M17: the constraint was never measured. Measure it in "
                f"flow/characterize.py (dff_constraints). Note the reachability "
                f"check above PASSED — the field is wired up fine, the number "
                f"in it is a placeholder."]
    print(f"  {lib.name}: hold rise {declared[0]*1000:+.3f} ps / fall "
          f"{declared[1]*1000:+.3f} ps — OpenSTA applied {used['real']*1000:+.3f} "
          f"ps on the worst min path (slack {slacks['real']:.5f} ns), and a "
          f"0 -> {PROBE} ns sweep moves it by {shift:.5f} ns")
    return []


def internal_power(log):
    """The 'Total' row of report_power; column 1 is internal power."""
    tail = log[log.find("@@@POWER_START"):]
    m = re.search(r"^Total\s+(\S+)", tail, re.M)
    return float(m.group(1)) if m else None


def check(lib):
    WORK.mkdir(parents=True, exist_ok=True)
    # copyfile, not copy: copy() also copies the mode bits, and chmod on the
    # /mnt/c DrvFs mount raises EPERM, so `copy` makes this guard unrunnable
    # locally under WSL — which is the only way to run it on the Windows box.
    shutil.copyfile(lib, WORK / "own.lib")
    (WORK / "fanout_probe.v").write_text(netlist())
    (WORK / "fanout_probe.sdc").write_text(SDC)
    (WORK / "probe.tcl").write_text(TCL)
    log = run_sta()

    fails = []
    m = re.search(r"@@@FANOUT (\d+)", log)
    if not m:
        print(log[-3000:])
        return [f"{lib.name}: OpenSTA did not complete — no violation count"]
    count = int(m.group(1))

    # M15. The over-limit driver must be reported, and it must be the ONLY one.
    if count == 0:
        fails.append(
            f"{lib.name}: a {OVER}-sink net against set_max_fanout {LIMIT} "
            f"reported ZERO violations. The max-fanout check cannot fail, so "
            f"any 0 it reports downstream means nothing. This is defect M15: "
            f"the library is missing `default_fanout_load` (and per-pin "
            f"`fanout_load`), so OpenSTA sums every net's fanout to 0.0.")
    elif count != 1:
        fails.append(
            f"{lib.name}: expected exactly 1 max-fanout violation "
            f"(the {OVER}-sink net), got {count}. If the {UNDER}-sink net is "
            f"also flagged the check is wedged at 'violated' and is no more "
            f"informative than one wedged at 'clean'.")
    if f"drv_under/Y" in log and re.search(r"drv_under/Y.*VIOLATED", log):
        fails.append(f"{lib.name}: the {UNDER}-sink net (under the limit of "
                     f"{LIMIT}) was reported as violating.")

    # M16. A dropped table is announced once and then never again.
    bad = sorted(set(TEMPLATE_WARN.findall(log)))
    if bad:
        fails.append(
            f"{lib.name}: OpenSTA could not resolve table template(s) "
            f"{', '.join(bad)}, so it SILENTLY DISCARDED every table that "
            f"references them. This is defect M16: power tables must be "
            f"declared with `power_lut_template`, timing tables with "
            f"`lu_table_template` — they are separate namespaces.")
    ip = internal_power(log)
    if ip is None:
        fails.append(f"{lib.name}: report_power produced no Total row.")
    elif ip <= 0.0:
        fails.append(
            f"{lib.name}: reported internal power is {ip}, but this library "
            f"characterizes internal_power for every arc. Zero means the "
            f"tables were parsed and thrown away (M16).")

    if not fails:
        print(f"  {lib.name}: fanout check fires at {OVER} and stays quiet at "
              f"{UNDER}; all templates resolve; internal power {ip:.3e} W")
    return fails


def main():
    if len(sys.argv) > 1:
        libs = [Path(p) for p in sys.argv[1:]]
    else:
        libs = sorted(OUT.glob("own_hardening_*C_*v*.lib"))
    if not libs:
        sys.exit("FAIL: no corner hardening liberties in out/ — run "
                 "characterize.py then make_hardening.py")

    print(f"probing {len(libs)} liberty file(s) with OpenSTA "
          f"({OVER}-sink and {UNDER}-sink nets, set_max_fanout {LIMIT}; "
          f"two-flop hold probe):")
    fails = [f for lib in libs for f in check(lib) + check_hold(lib)]
    if fails:
        print("\nFAIL — the tool cannot see what the library declares:")
        for f in fails:
            print(f"  * {f}")
        sys.exit(1)
    print("\nPASS: every corner liberty is legible to OpenSTA — the max-fanout "
          "check is capable of failing, and no table is silently discarded.")


if __name__ == "__main__":
    main()
