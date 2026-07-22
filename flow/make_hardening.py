"""Phase 6 prep: gate-level netlist + hardening liberty.

Synthesis happens HERE (locally, reproducibly): combinational logic ->
our 7 cells, flops -> our DFF_X1 (the dfxtp_1-geometry svt flop — the
hybrid era is over). Only the tie cells (conb_1) remain foundry. The
committed gate netlist is the CI hardening job's input — CI does
place-and-route only.

Outputs:
  out/own_hardening.lib  — own.lib as the P&R timing library
  harden/cordic_gates.v  — the gate-level netlist
"""
import re
from pathlib import Path

from common import OUT, run_yosys

RTL = Path(__file__).resolve().parents[2] / "tt-cordic" / "src"
TOP = "tt_um_joonatanalanampa_cordic"
HARDEN = Path(__file__).resolve().parents[1] / "harden"
HARDEN.mkdir(exist_ok=True)

# DFF_X1 has a signoff layout now — the hardening liberty is own.lib
# verbatim (kept as a separate file so the CI input stays a stable path).
# abc gets a COMBINATIONAL-ONLY copy: handing it a liberty with a flop
# trips 'merged SCL conversion failed' and the mapper starts emitting
# raw $_XOR_/$_XNOR_ cells (measured — 100 unmapped gates).
PHYS_CELLS = """
  cell (TIE_X1) { area : 3.7536; cell_leakage_power : 0.001;
    pin (HI) { direction : output; function : "1";
      max_capacitance : 0.100; }
    pin (LO) { direction : output; function : "0";
      max_capacitance : 0.100; } }
  cell (WELLTAP_X1) { area : 1.2512; cell_leakage_power : 0; }
  cell (DIODE_X1) { area : 2.5024; cell_leakage_power : 0;
    pin (DIODE) { direction : input; capacitance : 0.001; } }
  cell (FILL_X1) { area : 1.2512; cell_leakage_power : 0; }
  cell (FILL_X2) { area : 2.5024; cell_leakage_power : 0; }
  cell (FILL_X4) { area : 5.0048; cell_leakage_power : 0; }
  cell (FILL_X8) { area : 10.0096; cell_leakage_power : 0; }
"""
def add_phys_cells(text):
    """Append the physical-only cells (fill/tap/diode) to a liberty file."""
    full = text.rstrip()
    assert full.endswith("}"), "unexpected liberty tail"
    return full[:-1] + PHYS_CELLS + "}\n"


lib = (OUT / "own.lib").read_text()
(OUT / "own_hardening.lib").write_text(add_phys_cells(lib))
comb, n = re.subn(r"\n  cell \(DFF_X1\).*?\n  \}(?=\n)", "", lib, flags=re.S)
assert n == 1, "DFF_X1 cell block not found"
(OUT / "own_abc.lib").write_text(comb)
print("own_hardening.lib (full) + own_abc.lib (comb-only) written")

# lib-v1.1: one hardening view per PVT corner, so P&R and STA see a real
# corner spread instead of nine byte-identical copies of the nominal library.
# ABC keeps mapping at the nominal corner -- technology mapping is a
# structural choice, not a signoff one.
corner_libs = sorted(p for p in OUT.glob("own_*C_*v*.lib")
                     if "hardening" not in p.name)
for src in corner_libs:
    corner = src.stem[len("own_"):]
    (OUT / f"own_hardening_{corner}.lib").write_text(
        add_phys_cells(src.read_text()))
if corner_libs:
    print(f"per-corner hardening libs: "
          f"{', '.join(p.stem[len('own_'):] for p in corner_libs)}")
else:
    print("WARNING: no per-corner libs found — run characterize.py for all "
          "PVTs to get a corner spread (see lib-v1.1)")

script = f"""
read_verilog -sv "{RTL / 'cordic.sv'}" "{RTL / 'project.sv'}"
hierarchy -top {TOP}
flatten
synth -top {TOP}
dfflegalize -cell $_DFF_P_ x
dfflibmap -liberty "{OUT / 'own_hardening.lib'}"
abc -liberty "{OUT / 'own_abc.lib'}"
opt_clean -purge
hilomap -hicell TIE_X1 HI -locell TIE_X1 LO
insbuf -buf BUF_X2 A Y
stat
write_verilog -noattr -nohex -nodec "{HARDEN / 'cordic_gates.v'}"
"""
log = run_yosys(script, "synth_hybrid")
# parse only the LAST stat block — `synth` prints an intermediate one
# full of $_XOR_/$_SDFF* gates that haven't met ABC yet (a phantom that
# cost one debugging session; $-cells are also excluded outright)
last_stat = log[log.rfind("Printing statistics"):]
counts = {}
for m in re.finditer(r"^\s+(\d+)\s+(\S+)\s*$", last_stat, re.M):
    name = m.group(2)
    if not name.startswith("$") and ("_X" in name or name.startswith("sky130")):
        counts[name] = int(m.group(1))
own = {k: v for k, v in counts.items() if not k.startswith("sky130")}
hd = {k: v for k, v in counts.items() if k.startswith("sky130")}
print("own cells :", sum(own.values()), own)
print("hd cells  :", sum(hd.values()), hd)
print(f"netlist -> {HARDEN / 'cordic_gates.v'}")
