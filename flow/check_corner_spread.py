"""Acceptance test for lib-v1.1: the timing corners must actually differ.

This exists because of a specific failure that is easy to ship and hard to
notice. The library was characterized at one PVT, that single Liberty view was
handed to LibreLane through EXTRA_LIBS (which the tool documents as "loaded
indiscriminately for all timing corners"), and the flow ran green: nine STA
corners, nine SDF files, every one of them byte-identical. Nothing failed.
The design just had no corner spread, so a measured-vs-predicted gap in
silicon could not be attributed to process, voltage or temperature -- there
was no error bar to judge it against.

So do not trust the config semantics; assert the property. Two things are
checked, in order of how badly they would bite:

  1. the per-corner Liberty files we generate really do carry different
     numbers (a cheap check that runs anywhere), and
  2. if a hardening run is present, the SDF written per corner differs too --
     which is the only proof that the corner-keyed LIB actually reached
     OpenROAD rather than being silently overridden by a nominal EXTRA_LIBS.

Usage:  python check_corner_spread.py [<runs/*/ dir>]
"""
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"

# a delay number inside an NLDM table
NUM = re.compile(r"-?\d+\.\d+")


def lib_fingerprint(path):
    """All table values in a liberty file, as a tuple."""
    vals = []
    for m in re.finditer(r"values\(([^;]*)\)", path.read_text(), re.S):
        vals.extend(float(x) for x in NUM.findall(m.group(1)))
    return tuple(vals)


def main():
    libs = sorted(OUT.glob("own_*C_*v*.lib"))
    libs = [p for p in libs if "hardening" not in p.name]
    if len(libs) < 2:
        sys.exit("FAIL: fewer than two per-corner liberty files in out/ — "
                 "run `python characterize.py` (all PVTs) first")

    print(f"per-corner liberty files ({len(libs)}):")
    fps = {}
    for p in libs:
        fp = lib_fingerprint(p)
        fps[p.name] = fp
        print(f"  {p.name:<32s} {len(fp):5d} table values, "
              f"mean {sum(fp)/len(fp):.4f} ns")
    if not fps:
        sys.exit("FAIL: no table values parsed")

    names = list(fps)
    sizes = {len(v) for v in fps.values()}
    if len(sizes) != 1:
        sys.exit(f"FAIL: corner libraries have different shapes {sizes} — "
                 "they must describe the same cells and tables")

    identical = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
                 if fps[a] == fps[b]]
    if identical:
        sys.exit(f"FAIL: byte-identical timing in {identical} — this is "
                 "exactly the bug lib-v1.1 exists to fix")

    # report the spread, since a spread of 0.001% would pass the test above
    # while being useless in practice
    base = names[0]
    worst = 0.0
    for n in names[1:]:
        rel = max(abs(y / x - 1) for x, y in zip(fps[base], fps[n]) if x)
        worst = max(worst, rel)
        print(f"  max |{n} / {base} - 1| = {100*rel:.1f}%")
    if worst < 0.05:
        sys.exit(f"FAIL: corner spread is only {100*worst:.2f}% — suspiciously "
                 "small for tt/ss/ff; are all three really different models?")
    print(f"PASS: liberty corners differ, worst-case spread {100*worst:.0f}%")

    # ---------------------------------------------------------------- SDF
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if run_dir is None:
        print("\n(no run directory given — skipping the SDF check)")
        return
    sdfs = sorted(run_dir.rglob("*.sdf"))
    if not sdfs:
        sys.exit(f"FAIL: no SDF files under {run_dir}")
    digests = {}
    for s in sdfs:
        digests.setdefault(s.read_bytes(), []).append(s.name)
    print(f"\nSDF: {len(sdfs)} files, {len(digests)} distinct")
    for names_ in digests.values():
        print(f"  {len(names_)}x  {names_[0]}")
    if len(digests) < 2:
        sys.exit("FAIL: every SDF corner is byte-identical — the corner-keyed "
                 "LIB did not reach OpenROAD (a nominal EXTRA_LIBS overriding "
                 "it would look exactly like this)")
    print("PASS: the hardened design has a real corner spread")


if __name__ == "__main__":
    main()
