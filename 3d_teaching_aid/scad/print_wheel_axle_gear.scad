// 齒輪 Wheel + axle gear (driven by the pinion). Prints flat, gear
// teeth up, decorative wheel disc down.
include <common.scad>
use <parts.scad>
translate([0, 0, 10])
    wheel_axle_gear(axle_d = WHEEL_AXLE_D);
