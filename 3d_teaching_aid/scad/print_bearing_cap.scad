// Part D - 軸承 Bearing end cap. Print this TWICE (one per frame end).
// Flipped so the wide disc sits on the bed and the lip points up —
// avoids the overhang a lip-down print would need supports for.
include <common.scad>
use <parts.scad>
translate([0, 0, CAP_T])
    rotate([180, 0, 0])
        bearing_cap();
