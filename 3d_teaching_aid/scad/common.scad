// ============================================================
// D29 牽引馬達教學模型 - 共用參數與輔助模組
// Shared parameters & helper modules for the traction-motor
// teaching aid, inspired by the "Type D29 Traction Motor"
// museum exhibit panel (Electromagnet Frame / Armature /
// Cables / Bearing / Gear).
// ============================================================

$fn = 72;

// ---- global fit ----
TOL      = 0.35;  // radial clearance for rotating/sliding fits
SCREW_D  = 3.2;    // M3 clearance hole
PILOT_D  = 2.6;    // M3 self-tap pilot hole (into a printed boss)
HEAD_D   = 6.4;    // M3 pan-head clearance
HEAD_H   = 3.2;

// ---- gears (齒輪 Gear drive to the wheel) ----
// MCAD's gear() sizes teeth from circular_pitch: pitch_diameter =
// number_of_teeth * circular_pitch / 180. Using the SAME circular
// pitch for both gears is what makes them mesh correctly.
GEAR_CIRC_PITCH = 360;
PINION_TEETH = 16;              // pitch dia. 32 mm -> on the armature
WHEEL_TEETH  = 32;              // pitch dia. 64 mm -> on the wheel axle
GEAR_THICK   = 6;
WHEEL_D      = 90;   // decorative "road wheel" disc driven by the axle gear
GEAR_CENTER_DIST = (PINION_TEETH + WHEEL_TEETH) * GEAR_CIRC_PITCH / 360; // = 48 mm

// ---- shaft / armature (Part B 電樞 Armature) ----
// Laid out sequentially along the shaft so nothing overlaps:
//   [0 .. BEARING_MARGIN]                bare shaft (near bearing journal)
//   [.. + COMM_LEN]                      commutator ring
//   [.. + GAP1]                          bare shaft / air gap
//   [.. + CORE_LEN]                      laminated core (sits inside the frame)
//   [.. + GAP2]                          bare shaft / air gap
//   [.. + DFLAT_LEN]                     D-flat drive end (the pinion sits on
//                                        the last GEAR_THICK mm of it, flush
//                                        with the shaft tip)
SHAFT_D       = 10;
BEARING_MARGIN = 8;
COMM_D        = 24;
COMM_LEN      = 16;
COMM_SEGS     = 12;
GAP1          = 8;
CORE_D        = 40;
CORE_LEN      = 50;
LAMINATION_N  = 12;   // number of simulated lamination grooves
GAP2          = 8;
DFLAT_LEN     = 24;    // length of the flat-sided drive end
DFLAT_CUT     = 2.6;   // material removed from round shaft to make the flat

COMM_Z        = BEARING_MARGIN;
CORE_Z        = COMM_Z + COMM_LEN + GAP1;
DFLAT_Z       = CORE_Z + CORE_LEN + GAP2;
SHAFT_LEN     = DFLAT_Z + DFLAT_LEN;
GEAR_Z        = SHAFT_LEN - GEAR_THICK;   // the pinion sits flush with the shaft tip
PIN_Z         = GEAR_Z + GEAR_THICK/2;    // retaining-pin hole, through the pinion's middle

// ---- frame / stator housing (Part A 磁框 Electromagnet Frame) ----
FRAME_ID     = CORE_D + 2*3.5;  // 3.5 mm air-gap each side
FRAME_WALL   = 7;
FRAME_OD     = FRAME_ID + 2*FRAME_WALL;
FRAME_LEN    = CORE_LEN + 20;
POLE_COUNT   = 4;
POLE_W       = 16;
POLE_PROJ    = 4;
// where the frame's own local z=0 sits once slid over the armature,
// so it is centred on the laminated core
FRAME_OFFSET = CORE_Z - (FRAME_LEN - CORE_LEN)/2;

// ---- bearing end caps (Part D 軸承 Bearing) ----
// slightly wider than the frame tube so the caps form a shoulder
// that rests against the stand's support collars
CAP_D        = FRAME_OD + 10;
CAP_T        = 9;
CAP_LIP_H    = 6;              // lip that sits inside the frame bore
BOLT_PCD     = FRAME_OD - 16;  // bolt circle diameter, 4 bolts

// ---- cable entry cover (Part C 引線 Cables) ----
CABLE_HOLE_D = 3.2;
CABLE_COUNT  = 4;

// ---- base display stand ----
// All shaft-axis parts (frame, armature, wheel axle) share ONE global
// layout: the shaft runs along +X at height SHAFT_HEIGHT. A part's own
// local Z axis (its "along the shaft" axis) is mapped onto global X by
// rotate([0,90,0]); its local z=0 lands at the given global X offset.
PLATE_W       = 200;
PLATE_D       = 150;
PLATE_T       = 6;
SHAFT_HEIGHT  = 55;   // height of the armature/wheel axle centreline above the base
WHEEL_AXLE_D  = 6;
COLLAR_OD     = FRAME_OD + 20;
COLLAR_T      = 10;

MOTOR_COLLAR_X1 = 40;                       // frame's local z=0 (near/commutator end)
MOTOR_COLLAR_X2 = MOTOR_COLLAR_X1 + FRAME_LEN;  // frame's local z=FRAME_LEN (far end)
ARMATURE_X0     = MOTOR_COLLAR_X1 - FRAME_OFFSET;  // armature's local z=0, in global X
GEAR_MESH_X     = ARMATURE_X0 + PIN_Z;      // global X where the pinion sits

WHEEL_POST_X1   = GEAR_MESH_X - 17;
WHEEL_POST_X2   = GEAR_MESH_X + 17;

// ---- text label helper ----
module label_text(txt, size=5.5, depth=0.8, font="WenQuanYi Zen Hei:style=Regular") {
    linear_extrude(height=depth)
        text(txt, size=size, halign="center", valign="center", font=font);
}

module bolt_clearance(h=20) {
    union() {
        cylinder(d=SCREW_D, h=h, center=true);
        translate([0,0,h/2-HEAD_H/2])
            cylinder(d=HEAD_D, h=HEAD_H+0.5, center=true);
    }
}

module bolt_pilot(h=20) {
    cylinder(d=PILOT_D, h=h);
}
