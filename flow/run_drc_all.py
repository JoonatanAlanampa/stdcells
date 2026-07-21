"""Phase 5 v2: KLayout DRC (sky130A_mr.drc deck: feol+beol+offgrid) for
every generated cell. Parses the lyrdb in Python — the v1 lesson: an
empty <items> element tricked PowerShell's @() into a phantom count."""
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from common import PDK, OUT

KLAYOUT = Path.home() / "AppData" / "Roaming" / "KLayout" / "klayout_app.exe"
DECK = PDK / "libs.tech" / "klayout" / "drc" / "sky130A_mr.drc"

CELLS = ["INV_X1", "INV_X2", "INV_X4", "BUF_X2", "BUF_X4",
         "NAND2_X1", "NOR2_X1"]

fails = {}
for name in sys.argv[1:] or CELLS:
    gds = OUT / f"{name.lower()}.gds"
    report = OUT / f"{name.lower()}_drc.lyrdb"
    cp = subprocess.run(
        [str(KLAYOUT), "-b", "-r", str(DECK),
         "-rd", f"input={gds}", "-rd", f"report={report}",
         "-rd", "feol=true", "-rd", "beol=true", "-rd", "offgrid=true"],
        capture_output=True, text=True, timeout=900)
    if not report.exists():
        print(f"{name:9s}: DRC RUN FAILED\n{cp.stdout[-800:]}{cp.stderr[-400:]}")
        fails[name] = -1
        continue
    root = ET.parse(report).getroot()
    items = root.findall(".//item")
    cats = Counter(i.findtext("category", "").strip("'") for i in items)
    if items:
        fails[name] = len(items)
        det = ", ".join(f"{c}:{n}" for c, n in cats.most_common())
        print(f"{name:9s}: {len(items)} violations  ({det})")
        for i in items[:6]:
            cat = i.findtext("category", "").strip("'")
            val = i.findtext(".//value") or ""
            print(f"    {cat}: {val}")
    else:
        print(f"{name:9s}: CLEAN")

if fails:
    sys.exit(f"DRC failures: {fails}")
print("ALL CELLS DRC CLEAN")
