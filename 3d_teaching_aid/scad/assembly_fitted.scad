// ============================================================
// D29 牽引馬達教學模型 - 組裝完成圖 (Fitted assembly)
// Shows every part mounted together on the base stand, ready to
// turn: turning the armature's commutator spins the pinion,
// which drives the wheel-axle gear and its display wheel.
// Render/inspect only — parts are still printed separately,
// see the print_*.scad files.
// ============================================================
include <common.scad>
use <parts.scad>

module shaft_mounted(x0) {
    translate([x0, PLATE_D/2, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            children();
}

// base stand (plate + collars + posts + nameplate)
base_stand();

// A - frame, threaded through both collars
color("seagreen")
    shaft_mounted(MOTOR_COLLAR_X1)
        frame_electromagnet();

// B - armature, centred inside the frame
color("mediumseagreen")
    shaft_mounted(ARMATURE_X0)
        armature();

// D - bearing caps at both ends of the frame
color("dimgray") {
    shaft_mounted(MOTOR_COLLAR_X1)
        rotate([180, 0, 0])
            bearing_cap();
    shaft_mounted(MOTOR_COLLAR_X2)
        bearing_cap(drive_end = true);
}

// C - cable entry cover over the frame's viewing window
color("darkslategray")
    translate([MOTOR_COLLAR_X1 + FRAME_LEN/2, PLATE_D/2 + FRAME_OD/2 - 1, SHAFT_HEIGHT])
        rotate([0, 0, -90])
            rotate([0, -90, 0])
                cable_cover();

// Gear - pinion on the armature's D-flat end
color("gold")
    shaft_mounted(ARMATURE_X0 + GEAR_Z)
        pinion_gear();

// Gear - wheel axle assembly (axle rod + driven gear/wheel)
color("silver")
    translate([WHEEL_POST_X1, PLATE_D/2 - GEAR_CENTER_DIST, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            axle(len = WHEEL_POST_X2 - WHEEL_POST_X1, d = WHEEL_AXLE_D);

color("gold")
    translate([GEAR_MESH_X, PLATE_D/2 - GEAR_CENTER_DIST, SHAFT_HEIGHT])
        rotate([0, 90, 0])
            translate([0, 0, -GEAR_THICK/2])
                wheel_axle_gear(axle_d = WHEEL_AXLE_D);
