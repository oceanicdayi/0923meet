// Part B - 電樞 Armature. Lies on its side on the bed.
include <common.scad>
use <parts.scad>
translate([0, 0, CORE_D/2])
    rotate([0, 90, 0])
        armature();
