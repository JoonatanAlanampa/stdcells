# Magic-native views + per-cell magic DRC for the own library.
# Run inside the librelane container:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc flow/magic_views.tcl
#
# Reads the signoff GDS, saves .mag views (mag/) and magic-LEF abstracts
# (maglef/), and runs magic's full DRC per cell, printing counts and the
# rule text of every violation — the diagnosis that decides whether
# magic's complaints about GDS-only custom cells are real or
# interpretation artifacts.

drc euclidean on
drc style drc(full)

gds read out/own_cells.gds

file mkdir mag maglef

set cells {INV_X1 INV_X2 INV_X4 BUF_X2 BUF_X4 NAND2_X1 NOR2_X1 DFF_X1}
set total 0
foreach name $cells {
    load $name
    select top cell
    drc check
    drc catchup
    set n [drc list count total]
    incr total $n
    puts "MAGICDRC $name $n"
    if {$n > 0} {
        set out [drc listall why]
        foreach {why boxes} $out {
            puts "  WHY $name: $why ([llength $boxes] shapes)"
        }
    }
    save mag/$name.mag
    lef write maglef/$name.lef
}
puts "MAGICDRC-TOTAL $total"
quit -noprompt
