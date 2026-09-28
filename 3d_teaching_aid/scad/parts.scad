// ============================================================
// D29 牽引馬達教學模型 - 零件模組
// Part modules for the traction-motor teaching aid.
// Labels follow the museum panel: A 磁框 / B 電樞 / C 引線 / D 軸承 / 齒輪
// ============================================================
include <common.scad>
use <MCAD/gears.scad>

// ------------------------------------------------------------
// Part A - 磁框 Electromagnet Frame (stator housing)
// A hollow tube with 4 inward "pole" ribs standing in for the
// field-coil poles, a cut-away viewing window so students can
// see the armature spin inside, and 4x M3 pilot bosses at each
// end for the bearing end caps. The tube rests in the stand's
// support collars (see motor_collar()).
// ------------------------------------------------------------
module frame_electromagnet(window = true) {
    difference() {
        union() {
            // main tube
            difference() {
                cylinder(d = FRAME_OD, h = FRAME_LEN);
                translate([0, 0, -1])
                    cylinder(d = FRAME_ID, h = FRAME_LEN + 2);
            }

            // 4 inward pole ribs (electromagnet poles)
            for (a = [0 : 360/POLE_COUNT : 359])
                rotate([0, 0, a + 45])
                    translate([FRAME_ID/2 - POLE_PROJ, -POLE_W/2,
                               FRAME_LEN/2 - CORE_LEN/2])
                        cube([POLE_PROJ + 1, POLE_W, CORE_LEN]);

            // pilot bosses for the two bearing end caps
            for (z = [0, FRAME_LEN])
                for (a = [45, 135, 225, 315])
                    rotate([0, 0, a])
                        translate([BOLT_PCD/2, 0, z])
                            cylinder(d = PILOT_D + 5,
                                     h = (z == 0 ? 1 : -1) * 10);
        }

        // pilot holes, drilled after the bosses exist
        for (z = [0, FRAME_LEN])
            for (a = [45, 135, 225, 315])
                rotate([0, 0, a])
                    translate([BOLT_PCD/2, 0, z])
                        translate([0, 0, (z == 0 ? -0.1 : -9.9)])
                            bolt_pilot(h = 10);

        // viewing window over the air-gap so the armature is visible
        if (window)
            translate([0, 0, FRAME_LEN/2])
                translate([-14, FRAME_OD/2 - FRAME_WALL - 1, -11])
                    cube([28, FRAME_WALL + 2, 22]);
    }

    // embossed callout letter on the outer wall, opposite the window
    translate([0, -(FRAME_OD/2 - 0.3), FRAME_LEN/2])
        rotate([90, 0, 0])
            label_text("A", size = 9, depth = 0.8);
}

// ------------------------------------------------------------
// Part B - 電樞 Armature (rotor)
// A shaft with a "laminated" core (grooved cylinder), a slotted
// commutator ring, and a D-flat drive end for the output gear.
// ------------------------------------------------------------
module armature() {
    // shaft
    color("silver")
    cylinder(d = SHAFT_D, h = SHAFT_LEN);

    // laminated core, centred on the shaft, sits inside the frame
    translate([0, 0, CORE_Z])
        difference() {
            cylinder(d = CORE_D, h = CORE_LEN);
            // circumferential lamination grooves
            for (i = [1 : LAMINATION_N - 1])
                translate([0, 0, i * CORE_LEN / LAMINATION_N])
                    cylinder(d = CORE_D + 1, h = 0.6, center = true);
        }

    // callout letter on the core's flat end face, offset from the shaft
    translate([0, CORE_D/2 - 9, CORE_Z + CORE_LEN - 0.01])
        label_text("B", size = 8, depth = 0.8);

    // commutator ring near the near end
    translate([0, 0, COMM_Z])
        difference() {
            cylinder(d = COMM_D, h = COMM_LEN);
            for (a = [0 : 360/COMM_SEGS : 359])
                rotate([0, 0, a])
                    translate([COMM_D/2 - 1.2, -0.4, -1])
                        cube([3, 0.8, COMM_LEN + 2]);
        }

    // D-flat drive end for the output gear
    translate([0, 0, DFLAT_Z])
        intersection() {
            cylinder(d = SHAFT_D, h = DFLAT_LEN);
            translate([-SHAFT_D, -SHAFT_D/2 + DFLAT_CUT, -1])
                cube([SHAFT_D * 2, SHAFT_D, DFLAT_LEN + 2]);
        }

    // retaining pin hole inside the D-flat zone (a bamboo skewer/pin
    // through this hole + the matching hole in the gear keeps the
    // gear from sliding off during classroom handling)
    translate([0, 0, PIN_Z])
        rotate([90, 0, 0])
            cylinder(d = 3, h = SHAFT_D + 2, center = true);
}

// ------------------------------------------------------------
// Part D - 軸承 Bearing (printed end-cap bearing housing)
// Bolts to the pilot bosses at each end of the frame; the centre
// bore supports the armature shaft. A ring of shallow grooves on
// the outward face mimics a ball bearing's raceway for teaching.
// ------------------------------------------------------------
module bearing_cap(drive_end = false) {
    difference() {
        union() {
            cylinder(d = CAP_D, h = CAP_T);
            // lip that registers inside the frame bore
            translate([0, 0, -CAP_LIP_H + 0.01])
                cylinder(d = FRAME_ID - 2*TOL, h = CAP_LIP_H);
        }

        // shaft bore
        translate([0, 0, -CAP_LIP_H - 1])
            cylinder(d = SHAFT_D + 2*TOL, h = CAP_T + CAP_LIP_H + 2);

        // decorative raceway grooves
        for (r = [CAP_D/2 - 10, CAP_D/2 - 15, CAP_D/2 - 20])
            translate([0, 0, CAP_T - 0.6])
                difference() {
                    cylinder(r = r + 0.4, h = 0.8);
                    cylinder(r = r - 0.4, h = 0.8);
                }

        // bolt clearance holes matching the frame's pilot bosses
        for (a = [45, 135, 225, 315])
            rotate([0, 0, a])
                translate([BOLT_PCD/2, 0, CAP_T/2])
                    bolt_clearance(h = CAP_T + 1);
    }

    translate([0, CAP_D/2 - 9, CAP_T + 0.01])
        label_text("D", size = 8, depth = 0.8);
}

// ------------------------------------------------------------
// Part C - 引線 Cables entry cover
// A small cover that clips onto the frame's viewing-window edge
// with 4 grommet holes; real hook-up wire threaded through the
// holes stands in for the motor's supply cables.
// ------------------------------------------------------------
module cable_cover() {
    w = 34; h = 26; t = 4;
    difference() {
        union() {
            translate([-w/2, -h/2, 0]) cube([w, h, t]);
            // snap ribs that grip the frame window edges
            translate([-w/2 - 1.2, -h/2, 0]) cube([1.2, h, t]);
            translate([w/2, -h/2, 0]) cube([1.2, h, t]);
        }
        for (x = [-9, -3, 3, 9])
            translate([x, 0, -1])
                cylinder(d = CABLE_HOLE_D, h = t + 2);
    }
    translate([0, h/2 - 5, t + 0.01])
        label_text("C", size = 6, depth = 0.7);
}

// ------------------------------------------------------------
// 齒輪 Gear drive — pinion (on the armature) + wheel axle gear
// (drives a display road wheel), reproducing the panel's note
// that the armature "drives the wheels ... through a gear drive".
// ------------------------------------------------------------
module pinion_gear() {
    difference() {
        linear_extrude(height = GEAR_THICK)
            gear(number_of_teeth = PINION_TEETH,
                 circular_pitch = GEAR_CIRC_PITCH);
        translate([0, 0, -1])
            cylinder(d = SHAFT_D + 2*TOL, h = GEAR_THICK + 2);
        // matching D-flat bore
        translate([0, 0, -1])
            intersection() {
                cylinder(d = SHAFT_D + 2*TOL, h = GEAR_THICK + 2);
                translate([-SHAFT_D, -SHAFT_D/2 + DFLAT_CUT + TOL, -1])
                    cube([SHAFT_D * 2, SHAFT_D, GEAR_THICK + 4]);
            }
        // retaining-pin hole aligned with the armature's cross hole
        translate([0, 0, GEAR_THICK - 3])
            rotate([90, 0, 0])
                cylinder(d = 3.2, h = SHAFT_D + 4, center = true);
    }
}

module wheel_axle_gear(axle_d = 6) {
    union() {
        difference() {
            linear_extrude(height = GEAR_THICK)
                gear(number_of_teeth = WHEEL_TEETH,
                     circular_pitch = GEAR_CIRC_PITCH);
            translate([0, 0, -1])
                cylinder(d = axle_d + 2*TOL, h = GEAR_THICK + 2);
        }
        // decorative road-wheel disc, echoing "drive the wheels"
        translate([0, 0, -10])
            difference() {
                cylinder(d = WHEEL_D, h = 10);
                translate([0, 0, -1])
                    cylinder(d = axle_d + 2*TOL, h = 12);
                for (a = [0:60:300])
                    rotate([0, 0, a])
                        translate([WHEEL_D/2 - 16, 0, -1])
                            cylinder(d = 10, h = 12);
            }
    }
}

module axle(len = 60, d = 6) {
    cylinder(d = d, h = len);
}

// ------------------------------------------------------------
// Base display stand
// A plate with two upright "C" collars that cradle the frame
// (Part A) — the wider bearing end-caps rest against the collar
// faces and stop the motor sliding out — plus a pair of posts
// that carry the wheel axle so its gear meshes with the pinion
// on the armature's D-flat end, and an engraved bilingual
// nameplate summarising the callouts, mirroring the museum
// panel's legend.
// ------------------------------------------------------------
module motor_collar() {
    difference() {
        union() {
            translate([-COLLAR_T/2, 0, 0])
                rotate([0, 90, 0])
                    cylinder(h = COLLAR_T, d = COLLAR_OD);
            // leg down to the base plate
            translate([-COLLAR_T/2, -4, -SHAFT_HEIGHT])
                cube([COLLAR_T, 8, SHAFT_HEIGHT]);
        }
        translate([-COLLAR_T/2 - 1, 0, 0])
            rotate([0, 90, 0])
                cylinder(h = COLLAR_T + 2, d = FRAME_OD + 2*TOL + 2);
        // open slot at the top so the frame can be pressed in
        translate([-COLLAR_T/2 - 1, -12, 0])
            cube([COLLAR_T + 2, 24, COLLAR_OD]);
    }
}

module wheel_axle_post() {
    difference() {
        union() {
            translate([-COLLAR_T/2, 0, 0])
                rotate([0, 90, 0])
                    cylinder(h = COLLAR_T, d = WHEEL_AXLE_D + 16);
            translate([-COLLAR_T/2, -4, -SHAFT_HEIGHT])
                cube([COLLAR_T, 8, SHAFT_HEIGHT]);
        }
        translate([-COLLAR_T/2 - 1, 0, 0])
            rotate([0, 90, 0])
                cylinder(h = COLLAR_T + 2, d = WHEEL_AXLE_D + 2*TOL);
        translate([-COLLAR_T/2 - 1, -6, 0])
            cube([COLLAR_T + 2, 12, WHEEL_AXLE_D + 16]);
    }
}

module base_stand() {
    difference() {
        hull()
            for (x = [8, PLATE_W - 8])
                for (y = [8, PLATE_D - 8])
                    translate([x, y, 0])
                        cylinder(r = 8, h = PLATE_T);

        // lighten the plate a little
        translate([PLATE_W/2, PLATE_D/2 - 5, PLATE_T - 2])
            cylinder(d = 30, h = 4);
    }

    translate([MOTOR_COLLAR_X1, PLATE_D/2, SHAFT_HEIGHT])
        motor_collar();
    translate([MOTOR_COLLAR_X2, PLATE_D/2, SHAFT_HEIGHT])
        motor_collar();

    translate([WHEEL_POST_X1, PLATE_D/2 - GEAR_CENTER_DIST, SHAFT_HEIGHT])
        wheel_axle_post();
    translate([WHEEL_POST_X2, PLATE_D/2 - GEAR_CENTER_DIST, SHAFT_HEIGHT])
        wheel_axle_post();

    // bilingual nameplate, legend follows the museum panel's callouts
    translate([PLATE_W/2, 16, PLATE_T])
        legend_nameplate();
}

module legend_nameplate() {
    linear_extrude(height = 0.7)
        union() {
            translate([0, 20]) text("D29 牽引馬達教學模型", size = 7,
                halign = "center", font = "WenQuanYi Zen Hei:style=Regular");
            translate([0, 11]) text("Type D29 Traction Motor - Teaching Model",
                size = 3.4, halign = "center", font = "Liberation Sans:style=Bold");
            translate([0, 0]) text(
                "A 磁框 Frame   B 電樞 Armature   C 引線 Cables   D 軸承 Bearing   齒輪 Gear",
                size = 3, halign = "center", font = "WenQuanYi Zen Hei:style=Regular");
        }
}
