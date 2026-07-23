# v3 off-bin gate-check: what does magic make of a RECTANGULAR nfet at
# W = 0.25 um (off-bin, sub-0.42) vs W = 0.42 um (the diff/tap.2 std floor)?
# Run inside the librelane container with -rcfile <sky130A.magicrc>. For each
# device: magic DRC (count + why) and the extracted netlist (device type +
# W/L). The KLayout manufacturing deck passed BOTH clean; magic's diff/tap.2
# is the real transistor-width gate the foundry enforces.

proc check_device {gdsfile cellname} {
    puts "=== DEVICE $cellname ==="
    gds read $gdsfile
    load $cellname
    select top cell
    puts "LOADED [cellname list self]  BBOX [box values]"

    # --- magic DRC (stricter than the KLayout manufacturing deck) ---
    # select top cell sets the box to the cell extent (proven in annular.tcl)
    drc euclidean on
    drc check
    drc catchup
    puts "MAGIC-DRC-COUNT $cellname [drc list count total]"
    puts "DRC-WHY-BEGIN $cellname"
    drc why
    puts "DRC-WHY-END $cellname"

    # --- device extraction: does it bind an nfet, and at what W/L? ---
    extract all
    ext2spice lvs
    ext2spice
    puts "NETLIST-BEGIN $cellname"
    if {[catch {set fp [open "$cellname.spice" r]} e]} {
        puts "NO-SPICE-FILE: $e"
    } else {
        puts [read $fp]
        close $fp
    }
    puts "NETLIST-END $cellname"
    puts "DEVICE-DONE $cellname"
}

check_device flow/offbin/nfet_w250.gds nfet_w250
check_device flow/offbin/nfet_w420.gds nfet_w420
puts "EXTRACT-ALL-DONE"
