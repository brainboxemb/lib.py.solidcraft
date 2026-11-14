"""Qualification: child dimensions intentionally derived from parent parameters."""


class ParentBlock:
    width = 120.0
    depth = 80.0
    HEIGHT = 10.0

    def build(self):
        return Box(self.width, self.depth, self.HEIGHT)


class DerivedChild:
    width = 60.0
    depth = 40.0
    HEIGHT = 6.0

    def build(self):
        return Box(self.width, self.depth, self.HEIGHT)


class ParentDerivedChildSize:
    base_width = 120.0
    base_depth = 80.0

    def build(self):
        parent = ParentBlock(
            width=self.base_width,
            depth=self.base_depth,
            name="parent",
        )
        child = DerivedChild(
            width=half(self.base_width),
            depth=half(self.base_depth),
            name="child",
        ).move(z=20)

        return parent + child


ParentDerivedChildSize()
