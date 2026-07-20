"""Phase 6 prep: hybrid gate-level netlist + hardening liberty.

Synthesis happens HERE (locally, reproducibly, with full control over
which library maps what): combinational logic -> our 7 verified cells,
flops -> the foundry's dfxtp_1 (see README: the DFF hybrid decision).
The committed gate netlist is the CI hardening job's input — CI does
place-and-route only.

Outputs:
  out/own_hardening.lib  — own.lib minus the layout-less DFF_X1
  harden/cordic_gates.v  — the hybrid gate-level netlist
"""
import re
from pathlib import Path

from common import OUT, HD_LIB, run_yosys

RTL = Path(__file__).resolve().parents[2] / "tt-cordic" / "src"
TOP = "tt_um_joonatanalanampa_cordic"
HARDEN = Path(__file__).resolve().parents[1] / "harden"
HARDEN.mkdir(exist_ok=True)

# strip the DFF_X1 cell (characterized but layout-less) from the liberty
lib = (OUT / "own.lib").read_text()
lib2, n = re.subn(r"\n  cell \(DFF_X1\).*?\n  \}(?=\n)", "", lib,
                  flags=re.S)
assert n == 1, "DFF_X1 cell block not found/removed"
(OUT / "own_hardening.lib").write_text(lib2)
print(f"own_hardening.lib written ({n} sequential cell removed)")

script = f"""
read_verilog -sv "{RTL / 'cordic.sv'}" "{RTL / 'project.sv'}"
hierarchy -top {TOP}
flatten
synth -top {TOP}
dfflegalize -cell $_DFF_P_ x
dfflibmap -liberty "{HD_LIB}"
abc -liberty "{OUT / 'own_hardening.lib'}"
opt_clean -purge
hilomap -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO
insbuf -buf BUF_X2 A Y
stat
write_verilog -noattr -nohex -nodec "{HARDEN / 'cordic_gates.v'}"
"""
log = run_yosys(script, "synth_hybrid")
counts = {}
for m in re.finditer(r"^\s+(\S+)\s+(\d+)\s*$", log, re.M):
    if not m.group(1).startswith("$"):
        counts[m.group(1)] = int(m.group(2))
own = {k: v for k, v in counts.items() if not k.startswith("sky130")}
hd = {k: v for k, v in counts.items() if k.startswith("sky130")}
print("own cells :", sum(own.values()), own)
print("hd cells  :", sum(hd.values()), hd)
print(f"netlist -> {HARDEN / 'cordic_gates.v'}")
