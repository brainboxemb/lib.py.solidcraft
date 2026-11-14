"""Parameter scope qualification: implicit component parameters and inherited bindings."""


class Panel:
    width = 40.0
    DEPTH = 20.0
    HEIGHT = 10.0

    def build(self):
        return Box(self.width, self.DEPTH, self.HEIGHT)


class ParameterScope:
    shared_width = 80.0

    def build(self):
        local = Panel(name="local").move(x=0)
        override = Panel(width=60.0, name="override").move(x=100)

        shared_a = Panel(width=self.shared_width, name="shared_a").move(x=220)
        shared_b = Panel(width=self.shared_width, name="shared_b").move(x=340)

        derived = Panel(
            width=half(self.shared_width),
            name="derived",
        ).move(x=460)

        return local + override + shared_a + shared_b + derived


ParameterScope()
