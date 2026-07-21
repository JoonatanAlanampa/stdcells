# Magic-native views + per-cell magic DRC for the own library.
# Run inside the librelane container:
#   magic -dnull -noconsole -rcfile .../sky130A.magicrc flow/magic_views.tcl
#
# Reads the signoff GDS, saves .mag views (mag/) and magic-LEF abstracts
# (maglef/), and runs magic's full DRC per cell. Two FOUNDRY cells are
# checked first as a CONTROL group: rules that fire on hd's own
# silicon-proven cells at cell level (tap/latch-up connectivity rules —
# satisfied by tap cells at chip level, invisible standalone) are
# expected, not errors. The workflow compares: our cells must show NO
# rule category beyond the control set.

drc euclidean on
drc style drc(full)

set hd_gds $env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds
gds read $hd_gds
gds read out/own_cells.gds

file mkdir mag maglef

proc check_cell {name prefix} {
    load $name
    select top cell
    drc check
    drc catchup
    set n [drc list count total]
    puts "$prefix-DRC $name $n"
    if {$n > 0} {
        set out [drc listall why]
        foreach {why boxes} $out {
            puts "$prefix-WHY $name :: $why"
            foreach b $boxes {
                puts "$prefix-BOX $name :: $why :: $b"
            }
        }
    }
    return $n
}

# control: foundry cells standalone
foreach name {sky130_fd_sc_hd__inv_1 sky130_fd_sc_hd__dfxtp_1} {
    check_cell $name CONTROL
}

set cells {INV_X1 INV_X2 INV_X4 BUF_X2 BUF_X4 NAND2_X1 NOR2_X1 DFF_X1}
set total 0
foreach name $cells {
    incr total [check_cell $name OWN]
    save mag/$name.mag
    lef write maglef/$name.lef
}
puts "MAGICDRC-TOTAL $total"
quit -noprompt
