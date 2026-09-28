// ============================================================
// D29 牽引馬達教學模型 - 分解圖 (Exploded assembly, render only)
// Same layout as assembly_fitted.scad but with every part pulled
// apart along the shaft axis, echoing the museum panel's exploded
// diagram style. Preview/render only — not meant for printing.
// ============================================================
include <common.scad>
use <parts.scad>

EXP = 45; // explode gap

module shaft_mounted(x0) {
    translate([x0, PLATE_D/2, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            children();
}

base_stand();

color("seagreen")
    shaft_mounted(MOTOR_COLLAR_X1)
        frame_electromagnet();

color("mediumseagreen")
    shaft_mounted(ARMATURE_X0 - EXP)
        armature();

color("dimgray") {
    shaft_mounted(MOTOR_COLLAR_X1 - EXP)
        rotate([180, 0, 0])
            bearing_cap();
    shaft_mounted(MOTOR_COLLAR_X2 + EXP)
        bearing_cap(drive_end = true);
}

color("darkslategray")
    translate([MOTOR_COLLAR_X1 + FRAME_LEN/2, PLATE_D/2 + FRAME_OD/2 - 1 + EXP, SHAFT_HEIGHT])
        rotate([0, 0, -90])
            rotate([0, -90, 0])
                cable_cover();

color("gold")
    shaft_mounted(ARMATURE_X0 + GEAR_Z + EXP)
        pinion_gear();

color("silver")
    translate([WHEEL_POST_X1, PLATE_D/2 - GEAR_CENTER_DIST, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            axle(len = WHEEL_POST_X2 - WHEEL_POST_X1, d = WHEEL_AXLE_D);

color("gold")
    translate([GEAR_MESH_X, PLATE_D/2 - GEAR_CENTER_DIST - EXP, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            translate([0, 0, -GEAR_THICK/2])
                wheel_axle_gear(axle_d = WHEEL_AXLE_D);
