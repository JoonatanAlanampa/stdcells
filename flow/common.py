"""Shared paths and the ngspice runner."""
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PDK = HOME / ".ciel" / "ciel" / "sky130" / "versions" / \
    "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A"


def _short(p):
    """Windows 8.3 short path — ngspice's .lib parser splits on spaces."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 512):
        return Path(buf.value)
    return Path(p)


MODELS = _short(PDK / "libs.tech" / "combined" / "sky130.lib.spice")
HD_LIB = PDK / "libs.ref" / "sky130_fd_sc_hd" / "lib" / \
    "sky130_fd_sc_hd__tt_025C_1v80.lib"
NGSPICE = Path(__file__).resolve().parents[2] / "devphys" / "tools" / \
    "Spice64" / "bin" / "ngspice_con.exe"
YOSYS = HOME / "opt" / "oss-cad-suite" / "bin" / "yosys.exe"
OSS_BIN = HOME / "opt" / "oss-cad-suite" / "bin"
OSS_LIB = HOME / "opt" / "oss-cad-suite" / "lib"

OUT = Path(__file__).resolve().parents[1] / "out"
OUT.mkdir(exist_ok=True)

VDD = 1.8
TEMP = 25


def run_ngspice(netlist_text, tag):
    """Run a netlist in batch mode, return stdout (measures print there)."""
    f = OUT / f"{tag}.sp"
    f.write_text(netlist_text)
    cp = subprocess.run([str(NGSPICE), "-b", str(f)], capture_output=True,
                        text=True, cwd=OUT, timeout=600)
    (OUT / f"{tag}.log").write_text(cp.stdout + "\n===STDERR===\n" + cp.stderr)
    return cp.stdout


def parse_meas(stdout):
    """Collect 'name = value' measurement lines from ngspice output."""
    vals = {}
    for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", stdout, re.M):
        try:
            vals[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            pass
    return vals


def run_yosys(script_text, tag):
    f = OUT / f"{tag}.ys"
    f.write_text(script_text)
    env = dict(os.environ)
    env["PATH"] = f"{OSS_BIN};{OSS_LIB};" + env["PATH"]
    cp = subprocess.run([str(YOSYS), "-s", str(f)], capture_output=True,
                        text=True, env=env, timeout=1800)
    (OUT / f"{tag}.yslog").write_text(cp.stdout + "\n===STDERR===\n" + cp.stderr)
    if cp.returncode != 0:
        print(cp.stdout[-2000:])
        print(cp.stderr[-1000:])
        sys.exit(f"yosys failed ({tag})")
    return cp.stdout
