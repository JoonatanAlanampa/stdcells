#!/usr/bin/env python3
"""PVT comparison: custom stdcell library (lib-v1.1) vs sky130_fd_sc_hd.

Reads already-generated NLDM Liberty files (no re-characterization) and
compares, corner by corner, a 1:1 set of cells:

    INV_X1   <-> sky130_fd_sc_hd__inv_1
    NAND2_X1 <-> sky130_fd_sc_hd__nand2_1
    NOR2_X1  <-> sky130_fd_sc_hd__nor2_1
    DFF_X1   <-> sky130_fd_sc_hd__dfxtp_1

For every (cell, corner) it reports:
  * a representative cell_rise propagation delay, obtained by BILINEAR
    interpolation of the NLDM cell_rise grid to a COMMON operating point
    (input slew = 0.30 ns, output load = 0.025 pF) used identically for
    BOTH libraries -- apples to apples.  If the point lands outside a
    table's index range it is CLAMPED to the range (never extrapolated)
    and the clamp is surfaced.
  * cell_leakage_power and area straight from the Liberty.
  * the ss/ff delay ratio (corner spread / PVT sensitivity).

Everything is printed as a labelled text table.  Pure standard library.

Reproduce:  python flow/pvt_compare.py
"""

import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# CONFIG  (everything tunable lives here)
# --------------------------------------------------------------------------

# Common operating point for the apples-to-apples delay probe.
OP_SLEW = 0.30    # input net transition, ns  (Liberty index_1 axis)
OP_LOAD = 0.025   # total output net capacitance, pF  (Liberty index_2 axis)

# corner label -> Liberty corner token
CORNERS = [
    ("tt", "tt_025C_1v80"),
    ("ss", "ss_100C_1v60"),
    ("ff", "ff_n40C_1v95"),
]

# The 1:1 cell mapping.  arc = which timing arc to probe:
#   "first"       -> first input arc that carries a cell_rise (combinational)
#   "rising_edge" -> the CLK->Q rising_edge arc (flip-flop)
CELL_MAP = [
    {"label": "INV",   "own": "INV_X1",   "hd": "sky130_fd_sc_hd__inv_1",   "arc": "first"},
    {"label": "NAND2", "own": "NAND2_X1", "hd": "sky130_fd_sc_hd__nand2_1", "arc": "first"},
    {"label": "NOR2",  "own": "NOR2_X1",  "hd": "sky130_fd_sc_hd__nor2_1",  "arc": "first"},
    {"label": "DFF",   "own": "DFF_X1",   "hd": "sky130_fd_sc_hd__dfxtp_1", "arc": "rising_edge"},
]

# --------------------------------------------------------------------------
# Library file locations
# --------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent          # .../stdcells/flow
_STDCELLS = _HERE.parent                          # .../stdcells
OWN_OUT = _STDCELLS / "out"

# PDK path: honour flow/common.py as the source of truth, fall back to the
# same derivation if it cannot be imported (keeps this script self-contained).
def _pdk_path():
    try:
        sys.path.insert(0, str(_HERE))
        from common import PDK as _PDK  # type: ignore
        return Path(_PDK)
    except Exception:
        home = Path.home()
        return (home / ".ciel" / "ciel" / "sky130" / "versions" /
                "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7" / "sky130A")

PDK = _pdk_path()
HD_LIB_DIR = PDK / "libs.ref" / "sky130_fd_sc_hd" / "lib"


def own_lib_path(corner_token):
    return OWN_OUT / f"own_{corner_token}.lib"


def hd_lib_path(corner_token):
    return HD_LIB_DIR / f"sky130_fd_sc_hd__{corner_token}.lib"


# --------------------------------------------------------------------------
# Minimal, robust Liberty parser
# --------------------------------------------------------------------------
#
# We only ever parse a single cell's text (extracted by brace matching), so
# even the 13 MB foundry libs stay cheap.  The parser handles:
#   * nested groups            name (args) { ... }
#   * simple attributes        name : value ;
#   * complex attributes       name ( a, "b, c", ... ) ;   (index_1, values, ...)
#   * multi-line value strings continued with a trailing backslash
#   * /* ... */ comments
#   * quoted and unquoted group/argument names
#
# It is deliberately small; it is not a general Liberty validator.

class Node:
    __slots__ = ("name", "kind", "args", "value", "children")

    def __init__(self, name, kind, args=None, value=None):
        self.name = name
        self.kind = kind            # "group" | "attr" | "complex"
        self.args = args or []
        self.value = value
        self.children = []          # only for groups

    # -- convenience lookups --------------------------------------------
    def attr(self, name):
        for c in self.children:
            if c.kind == "attr" and c.name == name:
                return c.value
        return None

    def groups(self, name):
        return [c for c in self.children if c.kind == "group" and c.name == name]

    def complexes(self, name):
        return [c for c in self.children if c.kind == "complex" and c.name == name]

    def iter_groups(self, name):
        """Depth-first over all descendant groups with the given name."""
        for c in self.children:
            if c.kind == "group":
                if c.name == name:
                    yield c
                yield from c.iter_groups(name)


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# join backslash line-continuations into a single logical line
_CONT_RE = re.compile(r"\\[ \t]*\r?\n[ \t]*")
_TOKEN_RE = re.compile(r'"[^"]*"|[{}():;,]|[^\s{}():;,"]+')


def _strip_quotes(tok):
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return tok[1:-1]
    return tok


def tokenize(text):
    text = _COMMENT_RE.sub(" ", text)
    text = _CONT_RE.sub(" ", text)
    return _TOKEN_RE.findall(text)


def _parse_body(tokens, i):
    """Parse a group body; return (list_of_nodes, index_after_closing_brace)."""
    nodes = []
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t == "}":
            return nodes, i + 1
        name = t
        i += 1
        if i >= n:
            break
        nxt = tokens[i]
        if nxt == ":":                      # simple attribute
            i += 1
            val = _strip_quotes(tokens[i]); i += 1
            if i < n and tokens[i] == ";":
                i += 1
            nodes.append(Node(name, "attr", value=val))
        elif nxt == "(":                    # group or complex attribute
            i += 1
            args = []
            while i < n and tokens[i] != ")":
                if tokens[i] != ",":
                    args.append(_strip_quotes(tokens[i]))
                i += 1
            i += 1                          # consume ')'
            if i < n and tokens[i] == "{":  # -> group
                i += 1
                node = Node(name, "group", args=args)
                node.children, i = _parse_body(tokens, i)
                nodes.append(node)
            else:                           # -> complex attribute
                if i < n and tokens[i] == ";":
                    i += 1
                nodes.append(Node(name, "complex", args=args))
        else:
            # stray token (e.g. a lone ';'); skip it
            i += 1
    return nodes, i


def parse_cell(cell_text):
    """Parse a single 'cell (...) { ... }' block into a Node tree."""
    tokens = tokenize(cell_text)
    nodes, _ = _parse_body(tokens, 0)
    for nd in nodes:
        if nd.kind == "group" and nd.name == "cell":
            return nd
    raise ValueError("no cell group found in supplied text")


def extract_cell_text(lib_text, cell_name):
    """Return the exact 'cell (name) { ... }' substring via brace matching."""
    m = re.search(r'cell\s*\(\s*"?' + re.escape(cell_name) + r'"?\s*\)', lib_text)
    if not m:
        raise KeyError(f"cell {cell_name!r} not found")
    open_brace = lib_text.index("{", m.end())
    depth = 0
    in_str = False
    j = open_brace
    while j < len(lib_text):
        c = lib_text[j]
        if in_str:
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return lib_text[m.start():j + 1]
        j += 1
    raise ValueError(f"unbalanced braces for cell {cell_name!r}")


# --------------------------------------------------------------------------
# Library-level helpers
# --------------------------------------------------------------------------

def read_lib_header_units(lib_text):
    """Pull the time / leakage / capacitance units from the library header."""
    def grab(key):
        m = re.search(key + r'\s*:\s*"?([^";\n]+)"?\s*;', lib_text)
        return m.group(1).strip() if m else "?"
    cap = "?"
    m = re.search(r'capacitive_load_unit\s*\(\s*([0-9.]+)\s*,\s*"?([a-zA-Z]+)"?', lib_text)
    if m:
        cap = f"{float(m.group(1)):g} {m.group(2)}"
    return {
        "time": grab("time_unit"),
        "leakage": grab("leakage_power_unit"),
        "cap": cap,
    }


def get_cell(lib_text, cell_name):
    return parse_cell(extract_cell_text(lib_text, cell_name))


def select_cell_rise(cell_node, arc):
    """Return the cell_rise Node for the requested arc.

    arc == "first"       : first timing arc (input pin) carrying a cell_rise.
    arc == "rising_edge" : the CLK->Q rising_edge arc.
    """
    timings = list(cell_node.iter_groups("timing"))
    if arc == "rising_edge":
        for tg in timings:
            if tg.attr("timing_type") == "rising_edge" and tg.groups("cell_rise"):
                return tg.groups("cell_rise")[0]
        raise ValueError("no rising_edge cell_rise arc found")
    # arc == "first": first timing group that actually has a cell_rise table
    for tg in timings:
        cr = tg.groups("cell_rise")
        if cr:
            return cr[0]
    raise ValueError("no cell_rise arc found")


def _floats(csv_string):
    return [float(x) for x in csv_string.split(",") if x.strip()]


def parse_nldm_table(cell_rise_node):
    """Return (index_1 slew list, index_2 load list, grid[i][j])."""
    idx1 = cell_rise_node.complexes("index_1")
    idx2 = cell_rise_node.complexes("index_2")
    vals = cell_rise_node.complexes("values")
    if not (idx1 and idx2 and vals):
        raise ValueError("cell_rise table missing index_1/index_2/values")
    slew = _floats(idx1[0].args[0])
    load = _floats(idx2[0].args[0])
    grid = [_floats(row) for row in vals[0].args]        # grid[i(slew)][j(load)]
    if len(grid) != len(slew) or any(len(r) != len(load) for r in grid):
        raise ValueError("cell_rise grid shape mismatch vs index vectors")
    return slew, load, grid


# --------------------------------------------------------------------------
# Bilinear interpolation with explicit clamping
# --------------------------------------------------------------------------

def _bracket(axis, x):
    """Return (i, frac, clamped) so that value = axis[i] + frac*(axis[i+1]-axis[i]).

    Clamps to the axis range instead of extrapolating; flags when it does.
    """
    n = len(axis)
    if n == 1:
        return 0, 0.0, not (abs(x - axis[0]) < 1e-12)
    if x <= axis[0]:
        return 0, 0.0, x < axis[0] - 1e-12
    if x >= axis[-1]:
        return n - 2, 1.0, x > axis[-1] + 1e-12
    for i in range(n - 1):
        if axis[i] <= x <= axis[i + 1]:
            span = axis[i + 1] - axis[i]
            frac = 0.0 if span == 0 else (x - axis[i]) / span
            return i, frac, False
    return n - 2, 1.0, True  # defensive


def bilinear(slew_axis, load_axis, grid, slew, load):
    """Bilinear-interpolate grid at (slew, load).  Returns (value, clamped)."""
    i, fx, cx = _bracket(slew_axis, slew)
    j, fy, cy = _bracket(load_axis, load)
    g00 = grid[i][j]
    g10 = grid[i + 1][j] if i + 1 < len(grid) else grid[i][j]
    g01 = grid[i][j + 1] if j + 1 < len(grid[i]) else grid[i][j]
    g11 = (grid[i + 1][j + 1] if (i + 1 < len(grid) and j + 1 < len(grid[i + 1]))
           else grid[i][j])
    val = (g00 * (1 - fx) * (1 - fy) +
           g10 * fx * (1 - fy) +
           g01 * (1 - fx) * fy +
           g11 * fx * fy)
    return val, (cx or cy)


# --------------------------------------------------------------------------
# Extraction driver
# --------------------------------------------------------------------------

def probe(lib_text, cell_name, arc):
    """Return dict with area, leakage, interpolated delay (ns) and clamp flag."""
    cell = get_cell(lib_text, cell_name)
    area = cell.attr("area")
    leak = cell.attr("cell_leakage_power")
    cr = select_cell_rise(cell, arc)
    slew_axis, load_axis, grid = parse_nldm_table(cr)
    delay_ns, clamped = bilinear(slew_axis, load_axis, grid, OP_SLEW, OP_LOAD)
    return {
        "area": float(area) if area is not None else float("nan"),
        "leakage_nW": float(leak) if leak is not None else float("nan"),
        "delay_ns": delay_ns,
        "clamped": clamped,
        "slew_range": (slew_axis[0], slew_axis[-1]),
        "load_range": (load_axis[0], load_axis[-1]),
    }


def load_text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def collect():
    """Return nested results[label][lib][corner] = probe dict, plus units."""
    results = {}
    units = {}
    # cache lib texts so each file is read once
    own_texts = {ct: load_text(own_lib_path(ct)) for _, ct in CORNERS}
    hd_texts = {ct: load_text(hd_lib_path(ct)) for _, ct in CORNERS}
    units["own"] = read_lib_header_units(own_texts[CORNERS[0][1]])
    units["hd"] = read_lib_header_units(hd_texts[CORNERS[0][1]])

    for spec in CELL_MAP:
        label = spec["label"]
        results[label] = {"own": {}, "hd": {}}
        for corner, ct in CORNERS:
            results[label]["own"][corner] = probe(own_texts[ct], spec["own"], spec["arc"])
            results[label]["hd"][corner] = probe(hd_texts[ct], spec["hd"], spec["arc"])
    return results, units


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def ps(ns):
    return ns * 1000.0


def fmt(x, w=8, p=1):
    return f"{x:>{w}.{p}f}"


def print_report(results, units):
    W = 78
    print("=" * W)
    print("PVT COMPARISON  --  custom stdcell library (lib-v1.1) vs sky130_fd_sc_hd")
    print("=" * W)
    print(f"PDK        : {PDK}")
    print(f"Own libs   : {OWN_OUT}")
    print(f"Operating point (identical for both libs):")
    print(f"    input slew  (index_1) = {OP_SLEW:.3f} ns")
    print(f"    output load (index_2) = {OP_LOAD:.3f} pF")
    print(f"Units  own : time={units['own']['time']}  leakage={units['own']['leakage']}  "
          f"cap={units['own']['cap']}")
    print(f"Units  hd  : time={units['hd']['time']}  leakage={units['hd']['leakage']}  "
          f"cap={units['hd']['cap']}")
    print(f"Cell map   : " + ", ".join(f"{s['own']}<->{s['hd']}" for s in CELL_MAP))
    print()

    corners = [c for c, _ in CORNERS]

    # ---- Delay table (ps) --------------------------------------------
    print("-" * W)
    print(f"cell_rise propagation delay at ({OP_SLEW} ns / {OP_LOAD} pF)   [ps]")
    print("-" * W)
    hdr = f"{'cell':<7}" + "".join(f"{'own_'+c:>10}" for c in corners) \
                         + "".join(f"{'hd_'+c:>10}" for c in corners)
    print(hdr)
    any_clamp = False
    for spec in CELL_MAP:
        lab = spec["label"]
        row = f"{lab:<7}"
        for lib in ("own", "hd"):
            for c in corners:
                r = results[lab][lib][c]
                mark = "*" if r["clamped"] else " "
                any_clamp = any_clamp or r["clamped"]
                row += f"{ps(r['delay_ns']):>9.1f}{mark}"
        print(row)
    print(f"(* = operating point clamped to table range; "
          f"{'some values clamped' if any_clamp else 'no clamping occurred'})")
    print()

    # ---- Corner-spread table (ss/ff) ---------------------------------
    print("-" * W)
    print("Corner spread = delay(ss) / delay(ff)   (PVT sensitivity; higher = wider band)")
    print("-" * W)
    print(f"{'cell':<7}{'own ss/ff':>14}{'hd ss/ff':>14}{'own_faster?':>16}")
    for spec in CELL_MAP:
        lab = spec["label"]
        own_ratio = results[lab]["own"]["ss"]["delay_ns"] / results[lab]["own"]["ff"]["delay_ns"]
        hd_ratio = results[lab]["hd"]["ss"]["delay_ns"] / results[lab]["hd"]["ff"]["delay_ns"]
        tt_faster = "yes" if results[lab]["own"]["tt"]["delay_ns"] < results[lab]["hd"]["tt"]["delay_ns"] else "no"
        print(f"{lab:<7}{own_ratio:>14.3f}{hd_ratio:>14.3f}{tt_faster:>16}")
    print("(own_faster? = is custom cell faster than hd at the tt corner op-point)")
    print()

    # ---- Leakage table (nW) ------------------------------------------
    print("-" * W)
    print(f"cell_leakage_power   [own unit: {units['own']['leakage']}, hd unit: {units['hd']['leakage']}]")
    print("-" * W)
    print(f"{'cell':<7}" + "".join(f"{'own_'+c:>12}" for c in corners)
          + "".join(f"{'hd_'+c:>12}" for c in corners))
    for spec in CELL_MAP:
        lab = spec["label"]
        row = f"{lab:<7}"
        for lib in ("own", "hd"):
            for c in corners:
                row += f"{results[lab][lib][c]['leakage_nW']:>12.5f}"
        print(row)
    print()

    # ---- Area table (um^2) -------------------------------------------
    print("-" * W)
    print("area   [um^2]   (corner-independent; shown once per lib)")
    print("-" * W)
    print(f"{'cell':<7}{'own':>12}{'hd':>12}{'own/hd':>12}")
    for spec in CELL_MAP:
        lab = spec["label"]
        a_own = results[lab]["own"]["tt"]["area"]
        a_hd = results[lab]["hd"]["tt"]["area"]
        print(f"{lab:<7}{a_own:>12.4f}{a_hd:>12.4f}{a_own / a_hd:>12.3f}")
    print()

    # ---- Table-range diagnostics -------------------------------------
    print("-" * W)
    print("NLDM table index ranges (sanity: is the op-point inside the grid?)")
    print("-" * W)
    print(f"{'cell':<7}{'lib':<5}{'slew range [ns]':>22}{'load range [pF]':>22}")
    for spec in CELL_MAP:
        lab = spec["label"]
        for lib in ("own", "hd"):
            r = results[lab][lib]["tt"]
            sr = f"{r['slew_range'][0]:.4g}..{r['slew_range'][1]:.4g}"
            lr = f"{r['load_range'][0]:.4g}..{r['load_range'][1]:.4g}"
            print(f"{lab:<7}{lib:<5}{sr:>22}{lr:>22}")
    print("=" * W)


def main():
    results, units = collect()
    print_report(results, units)


if __name__ == "__main__":
    main()
