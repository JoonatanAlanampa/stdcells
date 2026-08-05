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


def run_sta():
    if shutil.which("sta"):
        cmd = ["sta", "-no_init", "-exit", "probe.tcl"]
    elif shutil.which("docker"):
        cmd = ["docker", "run", "--rm", "-v", f"{WORK}:/w", "-w", "/w",
               IMAGE, "sta", "-no_init", "-exit", "probe.tcl"]
    else:
        sys.exit("FAIL: neither `sta` nor `docker` on PATH — cannot run this "
                 "guard. On the Windows box, run it from inside WSL.")
    cp = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True)
    return cp.stdout + cp.stderr


def internal_power(log):
    """The 'Total' row of report_power; column 1 is internal power."""
    tail = log[log.find("@@@POWER_START"):]
    m = re.search(r"^Total\s+(\S+)", tail, re.M)
    return float(m.group(1)) if m else None


def check(lib):
    WORK.mkdir(parents=True, exist_ok=True)
    shutil.copy(lib, WORK / "own.lib")
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
          f"({OVER}-sink and {UNDER}-sink nets, set_max_fanout {LIMIT}):")
    fails = [f for lib in libs for f in check(lib)]
    if fails:
        print("\nFAIL — the tool cannot see what the library declares:")
        for f in fails:
            print(f"  * {f}")
        sys.exit(1)
    print("\nPASS: every corner liberty is legible to OpenSTA — the max-fanout "
          "check is capable of failing, and no table is silently discarded.")


if __name__ == "__main__":
    main()
