class Board:
    width = 40.0
    height = 20.0
    depth = 12.0

    def build(self):
        half_width = half(self.width)
        with Sketch(name="Profile", plane="XZ") as sketch:
            Polygon2D(
                [
                    ("lower_left", (-half_width, 0)),
                    ("lower_right", (half_width, 0)),
                    ("upper_right", (half_width, self.height)),
                    ("upper_left", (-half_width, self.height)),
                ],
                plane="XZ",
                world=True,
            )
        return sketch.extrude(
            self.depth,
            direction=Direction.POSITIVE,
        ).with_material(
            "test board",
            density_g_cm3=0.55,
        )


class Marker:
    def build(self):
        return Box(10, 10, 10)


class XzAnchor:
    board_width = 40.0
    board_height = 20.0

    def build(self):
        board = Board(
            width=self.board_width,
            height=self.board_height,
        )
        right_marker = Marker().attach(
            board,
            parent=Anchor.FRONT_TOP_RIGHT,
            child=Anchor.BACK_TOP_RIGHT,
        )
        left_marker = Marker().attach(
            board,
            parent=Anchor.FRONT_TOP_LEFT,
            child=Anchor.BACK_TOP_LEFT,
        )
        return board + right_marker + left_marker


XzAnchor()
