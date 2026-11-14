"""Eight vertical L-profiles: two on each rounded side corner."""


class FrameBlock:
    _width = 120.0
    _depth = 80.0
    _height = 60.0

    def build(self):
        return Box(
            self._width,
            self._depth,
            self._height,
        ).fillet(8, edges=Edges.VERTICAL)


class LProfile:
    ARM_LENGTH = 28.0
    THICKNESS = 4.0
    PROFILE_HEIGHT = 16.0

    def build(self):
        with Sketch(name="Profile", plane="XY") as sketch:
            Polygon2D(
                [
                    (0, 0),
                    (self.ARM_LENGTH, 0),
                    (self.ARM_LENGTH, -self.THICKNESS),
                    (-self.THICKNESS, -self.THICKNESS),
                    (-self.THICKNESS, self.ARM_LENGTH),
                    (0, self.ARM_LENGTH),
                ],
                plane="XY",
            )
        return sketch.extrude(
            self.PROFILE_HEIGHT,
            direction=Direction.POSITIVE,
        )


class EightCornerBrackets:
    frame_width = 120.0
    frame_depth = 80.0
    frame_height = 60.0

    def build(self):
        frame = FrameBlock(
            _width=self.frame_width,
            _depth=self.frame_depth,
            _height=self.frame_height,
        )
        profile = LProfile()

        frame_xy = AnchorFrame(
            origin=(0, 0, 0),
            z=Anchor.UP,
            x=Anchor.RIGHT,
        )
        profile_origin = AnchorFrame(
            origin=(0, 0, 0),
            z=Anchor.DOWN,
            x=Anchor.RIGHT,
        )

        half_width = half(self.frame_width)
        half_depth = half(self.frame_depth)
        top_height = self.frame_height - LProfile.PROFILE_HEIGHT

        def placed(x, y, angle, height):
            return profile.copy().attach(
                frame,
                parent=frame_xy,
                child=profile_origin,
                offset=(x, y),
                gap=height,
                angle=angle,
            )

        # Two short vertical angle profiles on each of the four rounded
        # side corners: one at the bottom and one at the top.
        front_left_bottom = placed(-half_width, -half_depth, 0, 0)
        front_left_top = placed(-half_width, -half_depth, 0, top_height)

        front_right_bottom = placed(half_width, -half_depth, 90, 0)
        front_right_top = placed(half_width, -half_depth, 90, top_height)

        rear_right_bottom = placed(half_width, half_depth, 180, 0)
        rear_right_top = placed(half_width, half_depth, 180, top_height)

        rear_left_bottom = placed(-half_width, half_depth, 270, 0)
        rear_left_top = placed(-half_width, half_depth, 270, top_height)

        return (
            frame
            + front_left_bottom + front_left_top
            + front_right_bottom + front_right_top
            + rear_right_bottom + rear_right_top
            + rear_left_bottom + rear_left_top
        )


EightCornerBrackets()
