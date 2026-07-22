# v3 scope-b GATE-CHECK: what does magic make of a ring-gate (annular) nfet?
# Run inside the librelane container with -rcfile <sky130A.magicrc> (loads the
# sky130 device-recognition tech). Reports: magic DRC, and the extracted
# netlist (device type + W/L) — the answer to "does an enclosed gate extract".

gds read flow/annular/annular_nfet.gds
load annular_nfet
select top cell
puts "LOADED-CELL [cellname list self]"
box values
puts "BBOX [box values]"

# --- magic DRC (its deck is stricter than the KLayout manufacturing deck) ---
drc euclidean on
drc check
drc catchup
puts "MAGIC-DRC-COUNT [drc list count total]"
puts "=== MAGIC-DRC-WHY ==="
drc why
puts "=== END-DRC-WHY ==="

# --- device extraction (the real question) ---
extract all
ext2spice lvs
ext2spice
puts "=== EXTRACTED-NETLIST ==="
if {[catch {set fp [open "annular_nfet.spice" r]} e]} {
    puts "NO-SPICE-FILE: $e"
} else {
    puts [read $fp]
    close $fp
}
puts "=== END-EXTRACTED-NETLIST ==="
puts "EXTRACT-DONE"
