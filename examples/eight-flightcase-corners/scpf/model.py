"""Eight trihedral flightcase corner protectors around one rounded case."""


class CaseBlock:
    _width = 120.0
    _depth = 80.0
    _height = 60.0

    def build(self):
        return Box(
            self._width,
            self._depth,
            self._height,
        ).fillet(8, edges=Edges.VERTICAL)


class FlightcaseCorner:
    # Fixed representative dimensions for this orientation qualification.
    # These values intentionally do not depend on CaseBlock dimensions.
    ARM = 20.0
    THICKNESS = 4.0
    OVERLAP = 0.5

    def build(self):
        arm = self.ARM
        t = self.THICKNESS
        overlap = self.OVERLAP

        # Neutral protector for a bottom/front/left corner.
        # The case interior is local +X/+Y/+Z; the three plates sit outside
        # the bottom, front and left faces and overlap slightly inside the cap.
        bottom = Box(arm, arm, t).move(
            x=half(arm),
            y=half(arm),
            z=-half(t),
        )
        front = Box(arm, t + overlap, arm + overlap).move(
            x=half(arm),
            y=half(overlap - t),
            z=half(arm - overlap),
        )
        side = Box(t + overlap, arm, arm + overlap).move(
            x=half(overlap - t),
            y=half(arm),
            z=half(arm - overlap),
        )
        return bottom + front + side


class EightFlightcaseCorners:
    case_width = 120.0
    case_depth = 80.0
    case_height = 60.0

    def build(self):
        case = CaseBlock(
            _width=self.case_width,
            _depth=self.case_depth,
            _height=self.case_height,
        )
        protector = FlightcaseCorner()

        case_xy = AnchorFrame(
            origin=(0, 0, 0),
            z=Anchor.UP,
            x=Anchor.RIGHT,
        )

        # These child frames are rotations of one neutral trihedral component.
        # Bottom corners keep local +Z upward; top corners map local +Z down
        # so the same protector wraps inward while its bottom plate becomes
        # the outside top plate.
        bottom_front_left = AnchorFrame(z=Anchor.DOWN, x=Anchor.RIGHT)
        bottom_front_right = AnchorFrame(z=Anchor.DOWN, x=Anchor.FRONT)
        bottom_rear_right = AnchorFrame(z=Anchor.DOWN, x=Anchor.LEFT)
        bottom_rear_left = AnchorFrame(z=Anchor.DOWN, x=Anchor.BACK)

        top_front_left = AnchorFrame(z=Anchor.UP, x=Anchor.BACK)
        top_front_right = AnchorFrame(z=Anchor.UP, x=Anchor.LEFT)
        top_rear_right = AnchorFrame(z=Anchor.UP, x=Anchor.FRONT)
        top_rear_left = AnchorFrame(z=Anchor.UP, x=Anchor.RIGHT)

        half_width = half(self.case_width)
        half_depth = half(self.case_depth)

        def placed(x, y, z, child_frame):
            return protector.copy().attach(
                case,
                parent=case_xy,
                child=child_frame,
                offset=(x, y),
                gap=z,
            )

        front_bottom_left = placed(
            -half_width, -half_depth, 0, bottom_front_left,
        )
        front_bottom_right = placed(
            half_width, -half_depth, 0, bottom_front_right,
        )
        rear_bottom_right = placed(
            half_width, half_depth, 0, bottom_rear_right,
        )
        rear_bottom_left = placed(
            -half_width, half_depth, 0, bottom_rear_left,
        )

        front_top_left = placed(
            -half_width, -half_depth, self.case_height, top_front_left,
        )
        front_top_right = placed(
            half_width, -half_depth, self.case_height, top_front_right,
        )
        rear_top_right = placed(
            half_width, half_depth, self.case_height, top_rear_right,
        )
        rear_top_left = placed(
            -half_width, half_depth, self.case_height, top_rear_left,
        )

        return (
            case
            + front_bottom_left + front_bottom_right
            + rear_bottom_right + rear_bottom_left
            + front_top_left + front_top_right
            + rear_top_right + rear_top_left
        )


EightFlightcaseCorners()
