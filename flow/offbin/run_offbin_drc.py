"""KLayout DRC (sky130A_mr.drc) for the off-bin nfet test devices, LOCAL.

The point of this check is the NEGATIVE one: the KLayout manufacturing deck has
no transistor-width rule, so it should pass a W = 0.25 um gated nfet CLEAN --
demonstrating that KLayout-clean != rule-clean, and that the real width verdict
can only come from magic (diff/tap.2), run in CI (offbin.yml). Mirrors
flow/run_drc_all.py's invocation + lyrdb parsing.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PDK

KLAYOUT = Path.home() / "AppData" / "Roaming" / "KLayout" / "klayout_app.exe"
DECK = PDK / "libs.tech" / "klayout" / "drc" / "sky130A_mr.drc"
HERE = Path(__file__).resolve().parent

GDS = sys.argv[1:] or ["nfet_w250.gds", "nfet_w420.gds"]

fails = {}
for g in GDS:
    gds = HERE / g
    report = HERE / (gds.stem + "_drc.lyrdb")
    cp = subprocess.run(
        [str(KLAYOUT), "-b", "-r", str(DECK),
         "-rd", f"input={gds}", "-rd", f"report={report}",
         "-rd", "feol=true", "-rd", "beol=true", "-rd", "offgrid=true"],
        capture_output=True, text=True, timeout=900)
    if not report.exists():
        print(f"{gds.stem:12s}: DRC RUN FAILED\n{cp.stdout[-800:]}{cp.stderr[-400:]}")
        fails[gds.stem] = -1
        continue
    items = ET.parse(report).getroot().findall(".//item")
    cats = Counter(i.findtext("category", "").strip("'") for i in items)
    if items:
        fails[gds.stem] = len(items)
        det = ", ".join(f"{c}:{n}" for c, n in cats.most_common())
        print(f"{gds.stem:12s}: {len(items)} violations  ({det})")
        for i in items[:8]:
            print(f"    {i.findtext('category', '').strip(chr(39))}: "
                  f"{i.findtext('.//value') or ''}")
    else:
        print(f"{gds.stem:12s}: KLAYOUT-CLEAN")

if fails:
    sys.exit(f"KLayout DRC violations: {fails}")
print("ALL OFF-BIN DEVICES KLAYOUT-CLEAN "
      "(the width issue is invisible to this deck -- magic decides in CI)")
