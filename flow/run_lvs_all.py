"""Phase 5b: KLayout LVS for every laid-out cell.

Motivation: the NAND2 power-to-output short that DRC merged silently —
LVS is the check that would have caught it, so it is now mandatory for
every cell. Uses the PDK's official sky130.lvs deck.

Reference netlists are emitted per cell from cells.py with two LVS-specific
adaptations: ports renamed to the layout labels (VPWR/VGND), and bulk
terminals moved to internal well/substrate nets (cells contain no taps —
the wells are floating at cell level, as in the foundry library; bulk
connectivity comes from tap cells at chip level).
"""
import re
import subprocess
import sys
from pathlib import Path

from common import PDK, OUT
from cells import LIBRARY

KLAYOUT = Path.home() / "AppData" / "Roaming" / "KLayout" / "klayout_app.exe"
DECK_SRC = PDK / "libs.tech" / "klayout" / "lvs" / "sky130.lvs"

LVS_DIR = OUT / "lvs"
LVS_DIR.mkdir(exist_ok=True)

# Auto-patch the deck: the SPICE reader UPPERCASES schematic device-class
# names while extraction uses lowercase — without an explicit equivalence
# the comparator pairs nothing and every net reports unmatched.
DECK = LVS_DIR / "sky130_patched.lvs"
_txt = DECK_SRC.read_text()
_eq = ('same_device_classes("sky130_fd_pr__nfet_01v8", '
       '"SKY130_FD_PR__NFET_01V8")\n'
       'same_device_classes("sky130_fd_pr__pfet_01v8", '
       '"SKY130_FD_PR__PFET_01V8")\n')
DECK.write_text(_txt.replace("#=== COMPARE ===", _eq + "#=== COMPARE ==="))

CELLS = ["INV_X1", "INV_X2", "INV_X4", "BUF_X2", "BUF_X4",
         "NAND2_X1", "NOR2_X1"]


def lvs_netlist(cell):
    """Reference subckt: VPWR/VGND ports; nwell bulk internal (floating
    well island); the p-substrate bulk is a PORT — the extractor exports
    it as one, since cells carry no taps (bulk connectivity arrives via
    tap cells at chip level, as in the foundry library)."""
    lines = [f".subckt {cell.name} " +
             " ".join(cell.inputs + [cell.output]) + " VPWR VGND VNB"]
    for i, (t, d, g, s, w) in enumerate(cell.mos):
        if t == "p":
            bulk, model = "nwell_i", "sky130_fd_pr__pfet_01v8"
        else:
            bulk, model = "VNB", "sky130_fd_pr__nfet_01v8"
        f = {"vdd": "VPWR", "vss": "VGND"}
        # M card (not X): the deck's SPICE reader treats X-prefixed device
        # instances as empty subcircuits and flattens them away.
        # Unit suffixes are MANDATORY: bare numbers are SPICE meters, and
        # the reader converts them to 1e6 um — nothing would ever pair.
        lines.append(f"M{i} {f.get(d, d)} {f.get(g, g)} {f.get(s, s)} "
                     f"{bulk} {model} L=0.15u W={w}u")
    lines.append(".ends")
    return "\n".join(lines) + "\n"


# Layout-equivalent forms for the series-chain cells: the layout folds
# each wide series device into two parallel chains with DISTINCT internal
# nodes — electrically identical to the characterization netlist (exact
# parallel duplication), topologically different, so LVS needs this form.
OVERRIDES = {
    "NAND2_X1": """.subckt NAND2_X1 A B Y VPWR VGND VNB
M0 Y A VPWR nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=1.7u
M1 Y B VPWR nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=1.7u
M2 VGND A m1 VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
M3 m1 B Y VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
M4 Y B m2 VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
M5 m2 A VGND VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
.ends
""",
    "NOR2_X1": """.subckt NOR2_X1 A B Y VPWR VGND VNB
M0 VPWR A p1 nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=0.85u
M1 p1 B Y nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=0.85u
M2 Y B p2 nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=0.85u
M3 p2 A VPWR nwell_i sky130_fd_pr__pfet_01v8 L=0.15u W=0.85u
M4 Y A VGND VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
M5 Y B VGND VNB sky130_fd_pr__nfet_01v8 L=0.15u W=0.65u
.ends
""",
}

results = {}
for name in CELLS:
    cell = next(c for c in LIBRARY if c.name == name)
    ref = LVS_DIR / f"{name}.spice"
    ref.write_text(OVERRIDES.get(name) or lvs_netlist(cell))
    gds = OUT / f"{name.lower()}.gds"
    cmd = [str(KLAYOUT), "-b", "-r", str(DECK),
           "-rd", f"input={gds}",
           "-rd", f"report={LVS_DIR / (name + '.lvsdb')}",
           "-rd", f"schematic={ref}",
           "-rd", f"target_netlist={LVS_DIR / (name + '_extracted.cir')}",
           "-rd", "thr=4", "-rd", "run_mode=deep",
           "-rd", "spice_net_names=false", "-rd", "spice_comments=false",
           "-rd", "scale=false", "-rd", "verbose=false",
           "-rd", "schematic_simplify=false", "-rd", "net_only=false",
           "-rd", "top_lvl_pins=false", "-rd", "combine=false",
           "-rd", "purge=false", "-rd", "purge_nets=false"]
    cp = subprocess.run(cmd, capture_output=True, text=True, cwd=LVS_DIR,
                        timeout=600)
    log = cp.stdout + cp.stderr
    (LVS_DIR / f"{name}.log").write_text(log)
    if re.search(r"Congratulations", log):
        results[name] = "MATCH"
    elif re.search(r"don'?t match|MISMATCH|ERROR", log, re.I):
        results[name] = "MISMATCH"
    else:
        results[name] = "UNKNOWN"
    print(f"{name:9s}: {results[name]}")

bad = [k for k, v in results.items() if v != "MATCH"]
if bad:
    sys.exit(f"LVS failures: {bad} — see out/lvs/*.log")
print("ALL CELLS LVS CLEAN")
