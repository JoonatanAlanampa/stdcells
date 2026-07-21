# Post-P&R same-net li spacing healing (KLayout batch:
#   klayout -b -r heal_li.py -rd input=chip.gds -rd output=healed.gds)
#
# Why: DRT's model has no same-net li spacing rule, so pin access may
# drop via pairs (or via-vs-pin-metal) 0.12-0.17 apart ON THE SAME NET.
# The manufacturing deck (li.3) has no same-net exemption — but for
# SAME-net shapes the legal fix is trivial: merge them with a bridge.
#
# Method (no guessing): build KLayout connectivity (li-licon-poly/diff
# is NOT needed; li-mcon-met1-via-met2-via2-met3 suffices for routing
# nets), find li shape pairs closer than 0.17, and:
#   - same net  -> insert a bridging rect spanning the gap (min-width
#                  checked), making them one polygon;
#   - different net -> REFUSE loudly: that is a real short-risk
#                  violation no one may paint over.
# The healed GDS is re-checked by the full official deck afterwards.
import pya

lay = pya.Layout()
lay.read(input)          # noqa: F821
top = lay.top_cell()

li = lay.layer(67, 20)
mcon = lay.layer(67, 44)
met1 = lay.layer(68, 20)
via = lay.layer(68, 44)
met2 = lay.layer(69, 20)
via2 = lay.layer(69, 44)
met3 = lay.layer(70, 20)

l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(lay, top, li))
r_li = l2n.make_layer(li, "li")
r_mcon = l2n.make_layer(mcon, "mcon")
r_met1 = l2n.make_layer(met1, "met1")
r_via = l2n.make_layer(via, "via")
r_met2 = l2n.make_layer(met2, "met2")
r_via2 = l2n.make_layer(via2, "via2")
r_met3 = l2n.make_layer(met3, "met3")
l2n.connect(r_li)
l2n.connect(r_mcon)
l2n.connect(r_met1)
l2n.connect(r_via)
l2n.connect(r_met2)
l2n.connect(r_via2)
l2n.connect(r_met3)
l2n.connect(r_li, r_mcon)
l2n.connect(r_mcon, r_met1)
l2n.connect(r_met1, r_via)
l2n.connect(r_via, r_met2)
l2n.connect(r_met2, r_via2)
l2n.connect(r_via2, r_met3)
l2n.extract_netlist()

# flat li with net annotation
flat = pya.Region(top.begin_shapes_rec(li))
flat.merge()

# pairs closer than 0.17 (edge check, euclidian)
SPACE = 170  # nm
viol = flat.space_check(SPACE, False, pya.Region.Euclidian, None, None, None)

net_of_point_cache = {}


def net_at(x, y):
    key = (x, y)
    if key in net_of_point_cache:
        return net_of_point_cache[key]
    # probe the extracted netlist for the net containing this li point
    n = l2n.probe_net(r_li, pya.DPoint(x / 1000.0, y / 1000.0))
    net_of_point_cache[key] = n.expanded_name() if n is not None else None
    return net_of_point_cache[key]


bridges = pya.Region()
real = []
npairs = 0
for ep in viol.each():
    npairs += 1
    e1, e2 = ep.first, ep.second
    p1 = e1.bbox().center()
    p2 = e2.bbox().center()
    # sample slightly inside each shape (shapes lie on opposite sides)
    n1 = net_at(p1.x, p1.y)
    n2 = net_at(p2.x, p2.y)
    if n1 is None or n2 is None or n1 != n2:
        real.append((str(ep), n1, n2))
        continue
    b = e1.bbox() + e2.bbox()          # joint bbox spans the gap
    if b.width() < 170:
        b = b.enlarged((170 - b.width()) // 2 + 5, 0)
    if b.height() < 170:
        b = b.enlarged(0, (170 - b.height()) // 2 + 5)
    bridges.insert(b)

assert not real, f"DIFFERENT-NET li pairs < 0.17um — refusing: {real[:5]}"

bridges.merge()
print(f"li spacing pairs: {npairs}, all same-net; bridge area: "
      f"{bridges.area()/1e6:.3f} um2")
top.shapes(li).insert(bridges)
lay.write(output)        # noqa: F821
print(f"wrote {output}")
