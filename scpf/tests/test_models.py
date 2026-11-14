"""Regression tests against reviewed SolidCraft 0.30.1 command fixtures."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from scpf.compiler import ModelError
from scpf.runner import run_script
from scpf import Sketch


ROOT = Path(__file__).resolve().parents[2]


class SCPFExamples(unittest.TestCase):
    def test_model_imports_shared_components_when_run_from_nested_directory(self):
        """The CLI accepts 'model.py' while cwd is models/<name>/scpf."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            components = root / "models" / "components"
            components.mkdir(parents=True)
            (components / "tiny.py").write_text(
                "from scpf.core import Box\n"
                "class TinyPanel:\n"
                "    def build(self):\n"
                "        return Box(20, 10, 2)\n",
                encoding="utf-8",
            )
            model_dir = root / "models" / "screen" / "scpf"
            model_dir.mkdir(parents=True)
            (model_dir / "model.py").write_text(
                "from scpf.runner import component\n"
                "from models.components.tiny import TinyPanel\n"
                "class Screen:\n"
                "    def build(self):\n"
                "        return component(TinyPanel)()\n"
                "Screen()\n",
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            original_paths = sys.path[:]
            try:
                os.chdir(model_dir)
                command_plan = run_script("model.py")
                names = [row["command"] for row in command_plan["commands"]]
                self.assertEqual(names.count("component.create"), 1)
                self.assertIn("solid.box", names)
                self.assertEqual(sys.path, original_paths)
            finally:
                os.chdir(original_cwd)
                for module in ("models.components.tiny", "models.components", "models"):
                    sys.modules.pop(module, None)


    def test_anchored_holes_example_compiles_to_one_holes_sketch(self):
        commands = run_script(
            ROOT / "examples/anchored-holes/scpf/model.py")["commands"]
        self.assertEqual(
            [c["params"]["name"] for c in commands
             if c["command"] == "sketch.create"],
            ["Base", "Holes"],
        )
        self.assertEqual(
            [c["params"]["center"] for c in commands
             if c["command"] == "sketch.circle.center"],
            [[50, 10], [50, 50]],
        )
        self.assertFalse(any(c["command"] == "solid.hole" for c in commands))
        self.assertEqual(commands[-1]["command"], "solid.extrude")
        self.assertEqual(commands[-1]["params"]["operation"], "cut")

    def test_named_edge_selection_and_explicit_edge_points(self):
        from scpf.core import Box, Edges
        body = Box(80, 50, 8)
        self.assertIs(body.fillet(6).data[2], Edges.VERTICAL)
        self.assertIs(body.fillet(6, edges=Edges.VERTICAL).data[2], Edges.VERTICAL)
        self.assertEqual(body.fillet(6, edges=[(0, 0, 4)]).data[2], [(0, 0, 4)])
        with self.assertRaises(ValueError):
            body.fillet(6, edges="vertical")

    def test_direction_enum_compiles_to_solidcraft_strings(self):
        from scpf.core import Circle2D, Direction
        from scpf.compiler import compile_model
        self.assertEqual(Direction.POSITIVE.value, "positive")
        self.assertEqual(Direction.NEGATIVE.value, "negative")
        with Sketch(plane="XY") as sketch:
            Circle2D(d=8)
        shape = sketch.extrude(8, direction=Direction.NEGATIVE)
        self.assertEqual(shape.data[-1], "negative")
        self.assertEqual(
            sketch.extrude(8, direction="negative").data[-1], "negative"
        )
        self.assertEqual(sketch.extrude(8).data[-1], "positive")
        with self.assertRaises(ValueError):
            sketch.extrude(8, direction="sideways")

    def test_anchor_directions_have_vectors_and_aliases(self):
        from scpf.core import Anchor, AnchorFrame

        self.assertIs(Anchor.UP, Anchor.TOP)
        self.assertIs(Anchor.DOWN, Anchor.BOTTOM)
        self.assertEqual(Anchor.RIGHT.vector, (1.0, 0.0, 0.0))
        self.assertEqual(Anchor.FRONT.vector, (0.0, -1.0, 0.0))
        self.assertEqual(
            Anchor.FRONT_TOP_LEFT.vector,
            (-1.0, -1.0, 1.0),
        )

        frame = AnchorFrame(z=Anchor.BACK, x=Anchor.DOWN)
        self.assertEqual(frame.z, (0.0, 1.0, 0.0))
        self.assertEqual(frame.x, (0.0, 0.0, -1.0))

    def test_cardinal_directions_combine_like_bosl2_selectors(self):
        from scpf import BOTTOM, FRONT, LEFT, RIGHT, TOP

        self.assertEqual((BOTTOM + LEFT).vector, (-1, 0, -1))
        self.assertEqual((TOP + RIGHT).vector, (1, 0, 1))
        self.assertEqual((FRONT + TOP + LEFT).vector, (-1, -1, 1))

        with self.assertRaisesRegex(ValueError, "same axis"):
            _ = LEFT + RIGHT

    def test_half_and_midpoint_preserve_symbolic_dimensions(self):
        from scpf import half, midpoint
        from scpf.core import Parameter, command_value

        width = Parameter("width", 100)
        left = Parameter("left", 20)
        right = Parameter("right", 80)

        self.assertEqual(half(10), 5)
        self.assertEqual(command_value(half(width)), "width / 2")
        self.assertEqual(
            command_value(midpoint(left, right)),
            "(left + (right)) / 2",
        )
        self.assertEqual(midpoint(10, 20), 15)

    def test_half_helpers_are_available_in_implicit_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class HalfBox:\n"
                "    width = 80.0\n"
                "    def build(self):\n"
                "        center = midpoint(0, self.width)\n"
                "        return Box(half(self.width), 10, 5).move(x=center)\n"
                "HalfBox()\n",
                encoding="utf-8",
            )
            generated = run_script(file)

        box = next(
            row["params"] for row in generated["commands"]
            if row["command"] == "solid.box"
        )
        self.assertEqual(box["length"], "width / 2")

    def test_removed_aliases_are_not_exposed(self):
        import scpf
        for name in ("Rectangle", "Circle", "Polygon", "Cube", "Box3D", "Cylinder3D", "Sphere3D"):
            self.assertFalse(hasattr(scpf, name), name)

    def test_attached_hole_pattern_builds_one_sketch_cut(self):
        from scpf.core import Axis, Depth, Faces, Hole, Rectangle2D, Parameter
        from scpf.compiler import compile_model
        width = Parameter("width", 100)
        depth = Parameter("depth", 60)
        thickness = Parameter("thickness", 10)
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(width, depth)
        plate = sketch.extrude(thickness)
        holes = Hole(d=8, depth=Depth.THROUGH_ALL).pattern(
            count=2, spacing=40, axis=Axis.Y
        ).on(plate, face=Faces.TOP)
        commands = compile_model(plate + holes, "Plate")["commands"]

        sketches = [c["params"]["name"] for c in commands
                    if c["command"] == "sketch.create"]
        self.assertEqual(sketches, ["Base", "Holes"])
        circles = [c["params"] for c in commands
                   if c["command"] == "sketch.circle.center"]
        self.assertEqual([c["center"] for c in circles], [[50, 10], [50, 50]])
        self.assertTrue(all(c["diameter"] == 8 for c in circles))
        self.assertFalse(any(c["command"] == "solid.hole" for c in commands))
        self.assertEqual(commands[-1]["command"], "solid.extrude")
        self.assertEqual(commands[-1]["params"]["operation"], "cut")
        self.assertEqual(commands[-1]["params"]["direction"], "positive")
        self.assertEqual(commands[-1]["params"]["distance"], "thickness")

    def test_hole_on_starts_at_exterior_top(self):
        from scpf.core import Anchor, Faces, Hole, Rectangle2D
        from scpf.compiler import compile_model, ModelError
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(80, 50)
        plate = sketch.extrude(8)
        attached = Hole(d=8).on(plate, face=Faces.TOP)
        commands = compile_model(plate + attached, "Plate")["commands"]
        self.assertEqual(commands[-1]["command"], "solid.extrude")
        self.assertEqual(commands[-1]["params"]["operation"], "cut")
        with self.assertRaises(ModelError):
            compile_model(
                plate - Hole(d=8).attach(plate, parent=Anchor.CENTER),
                "Plate",
            )
        with self.assertRaises(ValueError):
            Hole(d=-2)


    def test_on_uses_faces_without_exposing_assembly_anchors(self):
        from scpf.core import Anchor, Faces, Hole, Rectangle2D

        with Sketch(name="Base", plane="XY") as sketch:

            Rectangle2D(80, 50)

        plate = sketch.extrude(8)
        top = Hole(d=8).on(plate, face=Faces.TOP)
        bottom = Hole(d=8).on(plate, face=Faces.BOTTOM)

        self.assertEqual(top.kind, "anchored")
        self.assertEqual(bottom.kind, "anchored")
        self.assertIs(top.data[2], Anchor.TOP)
        self.assertIs(bottom.data[2], Anchor.BOTTOM)
        self.assertIs(top.data[3], Anchor.BOTTOM)
        self.assertIs(bottom.data[3], Anchor.BOTTOM)

    def test_symmetric_anchored_cylinder_pattern_follows_plate_dimensions(self):
        from scpf.core import Anchor, Axis, Cylinder, Rectangle2D
        from scpf.compiler import compile_model
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(100, 60)
        base = sketch.extrude(10)
        holes = Cylinder(d=8, h=12).pattern(
            count=2, spacing=40, axis=Axis.Y
        ).attach(base, parent=Anchor.CENTER, child=Anchor.CENTER)
        commands = compile_model(base - holes, "Plate")["commands"]
        cylinders = [c["params"] for c in commands
                     if c["command"] == "solid.cylinder"]
        self.assertEqual(len(cylinders), 2)
        self.assertEqual([c["base"][0] for c in cylinders], [50, 50])
        self.assertEqual([c["base"][1] for c in cylinders], [10, 50])
        self.assertEqual([c["base"][2] for c in cylinders], [-1, -1])
        self.assertEqual([c["operation"] for c in cylinders], ["cut", "cut"])

    def test_attached_boss_tracks_plate_top_and_offsets(self):
        from scpf.core import Cylinder, Faces, Rectangle2D, Parameter
        from scpf.compiler import compile_model
        width, depth, thickness = (
            Parameter("width", 80), Parameter("depth", 50),
            Parameter("thickness", 8)
        )
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(width, depth)
        base = sketch.extrude(thickness)
        boss = Cylinder(d=24, h=14).on(base, face=Faces.TOP)
        commands = compile_model(base + boss, "Plate")["commands"]
        cylinder = commands[-1]
        self.assertEqual(cylinder["command"], "solid.cylinder")
        self.assertEqual(cylinder["params"]["operation"], "join")
        self.assertEqual(cylinder["params"]["height"], 14)
        self.assertEqual(cylinder["params"]["diameter"], 24)
        self.assertEqual(cylinder["params"]["base"], [40.0, 25.0, 8.0])
        self.assertEqual(
            [row["params"]["name"] for row in commands
             if row["command"] == "sketch.create"],
            ["Base"],
        )

    def test_relative_anchor_rejects_unsupported_usage(self):
        from scpf.core import Anchor, Axis, Cylinder, Rectangle2D, Sphere
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(80, 50)
        base = sketch.extrude(8)
        with self.assertRaises(ValueError):
            Sphere(8).attach(base, parent=Anchor.TOP)
        with self.assertRaises(ValueError):
            Cylinder(d=8, h=10).pattern(count=2, spacing=40, axis=Axis.Z)
        with self.assertRaises(ValueError):
            Cylinder(d=8, h=10).attach(base, offset=(1, 2, 3))

    def test_cylinder_keyword_form_is_direct_3d_primitive(self):
        from scpf.core import Cylinder
        self.assertEqual(Cylinder(d=24, h=14).kind, "cylinder")
        self.assertEqual(Cylinder(d=24, h=14).at(40, 25, 8).kind, "placed3d")

    def test_cylinder_axis_lowers_directly_to_native_axis(self):
        from scpf.compiler import compile_model
        from scpf.core import Axis, Cylinder

        commands = compile_model(
            Cylinder(d=12, h=30, axis=Axis.X).at(-15, 0, 0),
            "Pin",
        )["commands"]
        cylinder = commands[-1]
        self.assertEqual(cylinder["command"], "solid.cylinder")
        self.assertEqual(cylinder["params"]["axis"], "X")
        self.assertEqual(cylinder["params"]["base"], [-15, 0, 0])

        with self.assertRaisesRegex(ValueError, "Cylinder axis"):
            Cylinder(d=12, h=30, axis="diagonal")

    def test_cylinder_at_places_center_on_centered_csg_body(self):
        from scpf.compiler import compile_model
        from scpf.core import Anchor, Axis, Box, Cylinder, Parameter, Sphere

        size = Parameter("size", 50)
        body = Sphere(size / 1.5) & Box(size, size, size)
        diameter = size / 1.5

        holes = (
            Cylinder(d=diameter, h=size, axis=Axis.X).at(body)
            + Cylinder(d=diameter, h=size, axis=Axis.Y).at(body)
            + Cylinder(d=diameter, h=size, axis=Axis.Z).at(body)
        )
        commands = compile_model(body - holes, "CsgCube")["commands"]

        cylinders = [
            command["params"]
            for command in commands
            if command["command"] == "solid.cylinder"
        ]
        self.assertEqual([item["axis"] for item in cylinders], ["X", "Y", "Z"])
        self.assertEqual(
            [item["base"] for item in cylinders],
            [
                ["-(size / 2)", 0, 0],
                [0, "-(size / 2)", 0],
                [0, 0, "-(size / 2)"],
            ],
        )

        with self.assertRaisesRegex(ValueError, "CENTER-to-CENTER"):
            Cylinder(d=10, h=20).at(
                body,
                anchor=Anchor.TOP,
                child=Anchor.CENTER,
            )

    def test_cylinder_standalone_native_command(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "model.py"
            script.write_text(
                "@dataclass\n"
                "class Pin:\n"
                "    diameter: float = 12\n"
                "    def build(self):\n"
                "        Cylinder(d=self.diameter, h=20).at(10, 5, 3)\n"
                "Pin()\n"
            )
            commands = run_script(script)["commands"]
        cylinder = commands[-1]
        self.assertEqual(cylinder["command"], "solid.cylinder")
        self.assertEqual(cylinder["params"]["base"], [10, 5, 3])
        self.assertEqual(cylinder["params"]["diameter"], "diameter")
        self.assertEqual(cylinder["params"]["operation"], "new")

    def test_plain_model_class_fields_become_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Cuboid:\n"
                "    length = 80.0\n"
                "    width = 50.0\n"
                "    height = 30.0\n"
                "    def build(self):\n"
                "        Box(self.length, self.width, self.height)\n"
                "Cuboid(width=60.0)\n"
            )
            generated = run_script(file)
        self.assertEqual(
            [c["params"]["name"] for c in generated["commands"][:3]],
            ["length", "width", "height"],
        )
        self.assertEqual(
            [c["params"]["expression"] for c in generated["commands"][:3]],
            ["80", "60", "30"],
        )

    def test_plain_model_class_accepts_positional_overrides_in_field_order(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Cuboid:\n"
                "    length = 80.0\n"
                "    width = 50.0\n"
                "    height = 30.0\n"
                "    def build(self):\n"
                "        Box(self.length, self.width, self.height)\n"
                "Cuboid(100.0, 70.0)\n"
            )
            generated = run_script(file)
        self.assertEqual(
            [c["params"]["expression"] for c in generated["commands"][:3]],
            ["100", "70", "30"],
        )

    def test_frozen_dataclass_build_with_implicit_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "@dataclass(frozen=True)\n"
                "class Cuboid:\n"
                "    size: float = 50\n"
                "    def __post_init__(self):\n"
                "        assert self.size > 0\n"
                "    def build(self):\n"
                "        Box(self.size, self.size, self.size).move(x=10)\n"
                "Cuboid(80)\n"
            )
            generated = run_script(file)
        self.assertEqual(generated["commands"][0]["params"]["name"], "size")
        self.assertEqual(generated["commands"][0]["params"]["expression"], "80")
        self.assertEqual(generated["commands"][1]["params"]["center"], [10, 0, 0])

    def test_dataclass_constructor_validates_before_symbolic_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "@dataclass\n"
                "class Cuboid:\n"
                "    size: float = 50\n"
                "    def __post_init__(self):\n"
                "        assert self.size > 0\n"
                "    def build(self):\n"
                "        Box(self.size, self.size, self.size)\n"
                "Cuboid(-5)\n"
            )
            with self.assertRaises(AssertionError):
                run_script(file)

    def test_dataclass_requires_build_method(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "@dataclass\n"
                "class Cuboid:\n"
                "    size: float = 50\n"
                "Cuboid()\n"
            )
            with self.assertRaisesRegex(TypeError, "must define build"):
                run_script(file)

    def test_dataclass_build_must_finish_with_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "@dataclass\n"
                "class Cuboid:\n"
                "    size: float = 50\n"
                "    def build(self):\n"
                "        body = Box(self.size, self.size, self.size)\n"
                "Cuboid()\n"
            )
            with self.assertRaisesRegex(TypeError, "finish with a Shape"):
                run_script(file)

    def test_arguments_are_editable_without_decorators(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def CsgCube(size=50.0):\n"
                "    return Sphere(size / 1.5) & Box(size, size, size)\n"
                "CsgCube(60.0)\n"
            )
            generated = run_script(file)
        self.assertEqual(generated["commands"][0]["params"]["expression"], "60")
        self.assertEqual(generated["commands"][1]["params"]["radius"], "size / 1.5")

    def test_pattern_requires_explicit_axes_and_valid_count(self):
        from scpf.core import Axis, Cylinder, Hole
        with self.assertRaises(TypeError):
            Hole(d=8).pattern(x=70, y=30)
        with self.assertRaises(ValueError):
            Cylinder(d=8, h=3).pattern(count=0, spacing=40, axis=Axis.X)
        with self.assertRaises(ValueError):
            Hole(d=8).pattern(count=2, spacing=40, axis=Axis.Z)

    def test_attached_hole_uses_sketch_while_explicit_at_can_be_native(self):
        from scpf.compiler import compile_model
        from scpf.core import Box, Rectangle2D, Polygon2D, Direction, Hole, Faces
        box = Box(80, 50, 8)
        with Sketch(name="Base", plane="XY") as sketch:
            Rectangle2D(80, 50)
        rectangle = sketch.extrude(8)
        for model in (
            box + Hole(d=6).on(box, face=Faces.TOP),
            rectangle + Hole(d=6).on(rectangle, face=Faces.TOP),
        ):
            commands = compile_model(model, "Widget")["commands"]
            self.assertEqual(commands[-1]["command"], "solid.extrude")
            self.assertEqual(commands[-1]["params"]["operation"], "cut")
            self.assertFalse(any(c["command"] == "solid.hole" for c in commands))

        with Sketch(plane="XZ") as sketch:
            Polygon2D(
                [(0, 0), (40, 0), (40, 6), (0, 6)], plane="XZ"
            )
        polygon = sketch.extrude(50, direction=Direction.NEGATIVE)
        commands = compile_model(
            polygon + Hole(d=6).at(20, -25, 0), "Widget"
        )["commands"]
        self.assertEqual(commands[-1]["command"], "solid.hole")

    def test_shell_uses_faces_without_reusing_anchor_semantics(self):
        from scpf.compiler import compile_model
        from scpf.core import Box, Faces
        commands = compile_model(
            Box(80, 50, 30).shell(2, open=Faces.TOP),
            "Enclosure",
        )["commands"]
        self.assertEqual(
            [c["command"] for c in commands],
            [
                "solid.box",
                "solid.shell",
            ],
        )
        self.assertEqual(commands[0]["params"]["body_name"], "Enclosure")
        self.assertEqual(commands[1]["params"]["faces"], [[0, 0, 30]])
        self.assertEqual(commands[1]["params"]["thickness"], 2)
        with self.assertRaises(ValueError):
            Box(80, 50, 30).shell(2, open=Faces.TOP).move(x=10)

    def test_bound_relative_offsets_resolve_against_parent_extents(self):
        from scpf.compiler import compile_model
        from scpf.core import Anchor, Boss, Box, Faces, X, Y
        body = Box(80, 50, 30).shell(2, open=Faces.TOP)

        minimum = Boss(d=7, h=12, hole_d=2.5).attach(
            body,
            parent=Anchor.INNER_BOTTOM,
            offset=(X.MIN + 10, Y.MIN + 10),
        )
        body = body + minimum

        maximum = Boss(d=7, h=12, hole_d=2.5).attach(
            body,
            parent=Anchor.INNER_BOTTOM,
            offset=(X.MAX - 10, Y.MAX - 10),
        )
        body = body + maximum

        commands = compile_model(body, "Enclosure")["commands"]
        bosses = [c for c in commands if c["command"] == "plastic.boss"]
        self.assertEqual(
            [boss["params"]["position"] for boss in bosses],
            [[-30, -15, 2], [30, 15, 2]],
        )

    def test_bound_relative_offsets_reject_wrong_axis(self):
        from scpf.core import Anchor, Boss, Box, Faces, X, Y
        body = Box(80, 50, 30).shell(2, open=Faces.TOP)
        with self.assertRaisesRegex(ValueError, "requires X bounds"):
            Boss(d=7, h=12, hole_d=2.5).attach(
                body,
                parent=Anchor.INNER_BOTTOM,
                offset=(Y.MIN + 10, Y.MIN + 10),
            )
        with self.assertRaisesRegex(ValueError, "requires Y bounds"):
            Boss(d=7, h=12, hole_d=2.5).attach(
                body,
                parent=Anchor.INNER_BOTTOM,
                offset=(X.MIN + 10, X.MIN + 10),
            )

    def test_inner_bottom_anchor_requires_shell(self):
        from scpf.compiler import compile_model, ModelError
        from scpf.core import Anchor, Boss, Box
        body = Box(80, 50, 30)
        boss = Boss(d=7, h=12, hole_d=2.5).attach(
            body,
            parent=Anchor.INNER_BOTTOM,
        )
        with self.assertRaises(ModelError):
            compile_model(body + boss, "Enclosure")

    def test_history_policy_can_lower_boss_to_sketches(self):
        commands = run_script(
            ROOT / "examples/history-policy/scpf/model.py"
        )["commands"]
        feature_commands = [
            c for c in commands if c["command"] != "parameters.add"
        ]
        self.assertEqual(
            [c["command"] for c in feature_commands],
            [
                "solid.box",
                "plastic.boss",
                "plastic.boss",
                "sketch.create",
                "sketch.circle.center",
                "sketch.finish",
                "solid.extrude",
                "sketch.create",
                "sketch.circle.center",
                "sketch.finish",
                "solid.extrude",
                "sketch.create",
                "sketch.circle.center",
                "sketch.finish",
                "solid.extrude",
            ],
        )
        self.assertEqual(
            [c["params"].get("name") for c in feature_commands
             if c["command"] == "sketch.create"],
            [
                "Boss",
                "Boss hole",
                "Explicit pad",
            ],
        )

    def test_rounded_rectangle_sketch_compiles_to_true_native_arcs(self):
        from scpf.core import Box, RoundedRectangle2D, Direction
        from scpf.explicit_sketch import Sketch
        from scpf.compiler import compile_model

        panel = Box(159.7, 319.71, 14.5).taper(from_z=2, inset=1.25)
        with Sketch(name="Rounded rear bays", on=panel) as bays:
            for y in (-120, -40, 40, 120):
                bays.add(RoundedRectangle2D(134.7, 59, 5),
                         offset=(-67.35, y - 29.5))
        panel = panel - bays.extrude(12.5, direction=Direction.NEGATIVE)
        commands = compile_model(panel, "Panel")["commands"]
        rounded = [cmd["params"] for cmd in commands
                   if cmd["command"] == "sketch.rectangle.rounded"]
        self.assertEqual(len(rounded), 4)
        self.assertTrue(all(part["radius"] == 5 for part in rounded))
        self.assertEqual(rounded[0]["p0"], [-67.35, -149.5])
        self.assertEqual(rounded[3]["p1"], [67.35, 149.5])
        self.assertEqual([cmd["command"] for cmd in commands].count("solid.loft"), 1)
        self.assertEqual(commands[-1]["params"]["operation"], "cut")

        for size in ((100, 60, 0), (100, 60, 30), (100, 60, -1),
                     (100, 60, 31), (0, 60, 5)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                RoundedRectangle2D(*size)

    def test_explicit_rear_bay_sketch_on_tapered_box(self):
        """Four rear window pockets retain the front plate and the editable loft."""
        from scpf.core import Box, Rectangle2D, Direction
        from scpf.explicit_sketch import Sketch
        from scpf.compiler import compile_model

        panel = Box(159.7, 319.71, 14.5).taper(from_z=2, inset=1.25)
        with Sketch(name="Rear electronics bays", on=panel, plane="XY",
                    origin=(0, 0, 14.5)) as rear:
            for center_y in (-120, -40, 40, 120):
                rear.add(Rectangle2D(134.7, 60.0),
                         offset=(-67.35, center_y - 30))
        panel = panel - rear.extrude(12.5, direction=Direction.NEGATIVE)
        commands = compile_model(panel, "Panel")["commands"]
        names = [cmd["command"] for cmd in commands]
        self.assertEqual(names.count("solid.loft"), 1)
        self.assertEqual(names.count("sketch.rectangle.two_point"), 7)
        pocket = next(i for i, cmd in enumerate(commands)
                      if cmd["command"] == "sketch.create"
                      and cmd["params"]["name"] == "Rear electronics bays")
        sketch = commands[pocket]["params"]
        self.assertEqual(sketch["plane"]["origin"], [0, 0, 14.5])
        rectangles = [cmd for cmd in commands[pocket + 1:]
                      if cmd["command"] == "sketch.rectangle.two_point"]
        self.assertEqual(len(rectangles), 4)
        self.assertEqual(rectangles[0]["params"]["p0"], [-67.35, -150])
        self.assertEqual(rectangles[-1]["params"]["p1"], [67.35, 150])
        self.assertEqual(commands[-1]["command"], "solid.extrude")
        self.assertEqual(commands[-1]["params"]["operation"], "cut")
        self.assertEqual(commands[-1]["params"]["direction"], "negative")
        self.assertEqual(commands[-1]["params"]["distance"], 12.5)

    def test_explicit_sketch_scope_requires_profiles_and_closes_before_extrude(self):
        from scpf.core import Box, Circle2D
        from scpf.explicit_sketch import Sketch

        body = Box(40, 30, 6)
        with self.assertRaisesRegex(ValueError, "at least one profile"):
            with Sketch(name="Empty", on=body):
                pass

        sketch = Sketch(name="Pad", on=body)
        with sketch:
            sketch.add(Circle2D(d=10))
            with self.assertRaisesRegex(ValueError, "before extruding"):
                sketch.extrude(5)

        self.assertEqual(sketch.extrude(5).kind, "explicit_sketch_extrusion")

    def test_history_policy_scope_does_not_leak(self):
        from scpf.core import Boss
        from scpf.history import History, behavior

        with behavior(history=History.SKETCH):
            inside = Boss(d=12, h=10)
        outside = Boss(d=12, h=10)

        self.assertIs(inside.history, History.SKETCH)
        self.assertIsNone(outside.history)

    def test_circle_profile_extrudes_with_explicit_sketch(self):
        from scpf.compiler import compile_model
        from scpf.core import Circle2D
        with Sketch(plane="XY") as sketch:
            Circle2D(d=12)
        commands = compile_model(sketch.extrude(8), "Pin")["commands"]
        self.assertEqual([c["command"] for c in commands],
                         ["sketch.create", "sketch.circle.center",
                          "sketch.finish", "solid.extrude"])
        self.assertEqual(commands[1]["params"]["diameter"], 12)

    def test_move_translates_a_csg_composite_without_changing_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def CsgCube(size=50.0):\n"
                "    body = Sphere(size / 1.5) & Box(size, size, size)\n"
                "    hole = Cylinder(d=size / 1.5, h=size).move(z=-10)\n"
                "    return (body - hole).move(x=10, y=20, z=30)\n"
                "CsgCube()\n"
            )
            document = run_script(file)
        commands = document["commands"]
        self.assertEqual(commands[1]["params"]["center"], [10, 20, 30])
        self.assertEqual(commands[2]["params"]["center"], [10, 20, 30])
        self.assertEqual(commands[3]["params"]["base"], [10, 20, 20])
        self.assertEqual(commands[3]["params"]["axis"], "Z")

    def test_cylinder_has_no_type_specific_orient_shortcut(self):
        from scpf.core import Cylinder
        self.assertFalse(hasattr(Cylinder(d=8, h=20), "orient"))

    def test_move_rejects_non_finite_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def Cuboid(size=50):\n"
                "    return Box(size, size, size).move(x=float('nan'))\n"
                "Cuboid()\n"
            )
            with self.assertRaises(ValueError):
                run_script(file)

    def test_model_function_implicit_shape_expression(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def Cuboid(size=50):\n"
                "    body = Box(size, size, size)\n"
                "    body.move(x=10)\n"
                "Cuboid()\n"
            )
            generated = run_script(file)
        self.assertEqual(generated["commands"][1]["params"]["center"], [10, 0, 0])

    def test_assignment_only_function_must_still_explicitly_return(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def Cuboid(size=50):\n"
                "    body = Box(size, size, size)\n"
                "Cuboid()\n"
            )
            with self.assertRaises(TypeError):
                run_script(file)

    def test_function_model_still_requires_explicit_final_call(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "def CubeModel(size=50):\n"
                "    return Box(size, size, size)\n"
            )
            with self.assertRaisesRegex(
                SyntaxError,
                "exactly one public class with build",
            ):
                run_script(file)

    def test_single_public_model_class_runs_directly_without_launcher_call(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "corner_bracket.py"
            file.write_text(
                "from scpf.core import Box\n"
                "class CornerBracket:\n"
                "    width = 24.0\n"
                "    def build(self):\n"
                "        return Box(self.width, 40, 40)\n",
                encoding="utf-8",
            )
            generated = run_script(file)

        self.assertEqual(
            [
                command["params"]["name"]
                for command in generated["commands"]
                if command["command"] == "parameters.add"
            ],
            ["width"],
        )
        self.assertTrue(
            any(command["command"] == "solid.box"
                for command in generated["commands"])
        )

    def test_direct_root_refuses_to_guess_between_public_model_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "models.py"
            file.write_text(
                "class First:\n"
                "    def build(self):\n"
                "        return Box(10, 10, 10)\n"
                "class Second:\n"
                "    def build(self):\n"
                "        return Box(20, 20, 20)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SyntaxError,
                "candidates: First, Second",
            ):
                run_script(file)



    def test_pv_is_explicit_escape_hatch_to_python_value(self):
        from scpf.core import Parameter, pv
        width = Parameter("width", 868.0)
        self.assertEqual(pv(width), 868.0)
        self.assertEqual(pv(width / 2), 434.0)

    def test_native_box_supports_directional_anchor_and_edge_selectors(self):
        from scpf import BOTTOM, FRONT, LEFT, RIGHT, Box
        from scpf.compiler import compile_model

        body = Box(100, 40, 12).at(
            0,
            10,
            5,
            anchor=FRONT + BOTTOM,
        ).fillet(
            4,
            edges=[
                BOTTOM + LEFT,
                BOTTOM + RIGHT,
            ],
        )

        commands = compile_model(body, "Board")["commands"]
        self.assertFalse(
            any(command["command"].startswith("sketch.") for command in commands)
        )

        box = next(
            command["params"]
            for command in commands
            if command["command"] == "solid.box"
        )
        self.assertEqual(box["corner"], [-50.0, 10, 5])

        fillet = next(
            command["params"]
            for command in commands
            if command["command"] == "solid.fillet"
        )
        self.assertEqual(
            fillet["edges"],
            [
                [-50.0, 30.0, 5.0],
                [50.0, 30.0, 5.0],
            ],
        )

    def test_positioned_box_keeps_symbolic_dimensions(self):
        from scpf import BOTTOM, FRONT, Box, Parameter
        from scpf.compiler import compile_model

        width = Parameter("width", 100)
        depth = Parameter("depth", 40)
        height = Parameter("height", 12)
        x = Parameter("x_position", 20)
        y = Parameter("y_position", 10)
        z = Parameter("z_position", 5)

        commands = compile_model(
            Box(width, depth, height).at(
                x,
                y,
                z,
                anchor=FRONT + BOTTOM,
            ),
            "Board",
        )["commands"]

        box = next(
            command["params"]
            for command in commands
            if command["command"] == "solid.box"
        )
        self.assertEqual(box["length"], "width")
        self.assertEqual(box["width"], "depth")
        self.assertEqual(box["height"], "height")
        self.assertIn("x_position", str(box["corner"][0]))
        self.assertIn("width", str(box["corner"][0]))
        self.assertEqual(box["corner"][1], "y_position")
        self.assertEqual(box["corner"][2], "z_position")

    def test_plain_model_fillet_keeps_radius_as_named_parameter(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Board:\n"
                "    width = 868.0\n"
                "    depth = 100.0\n"
                "    thickness = 12.0\n"
                "    corner_radius = 4.0\n"
                "    def build(self):\n"
                "        return Box(self.width, self.depth, self.thickness).fillet(\n"
                "            self.corner_radius, edges=Edges.VERTICAL)\n"
                "Board()\n"
            )
            generated = run_script(file)
        self.assertIn(
            {"command": "parameters.add",
             "params": {"name": "corner_radius", "expression": "4", "unit": "mm"}},
            generated["commands"],
        )
        fillet = next(c for c in generated["commands"]
                      if c["command"] == "solid.fillet")
        self.assertEqual(fillet["params"]["radius"], "corner_radius")


    def test_imported_class_can_be_the_root_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shared.py").write_text(
                "from scpf.core import Box\n"
                "class Bracket:\n"
                "    width = 24.0\n"
                "    _x_position = 0.0\n"
                "    def build(self):\n"
                "        return Box(self.width, 10, 10)\n",
                encoding="utf-8",
            )
            model = root / "model.py"
            model.write_text(
                "from shared import Bracket\n"
                "Bracket()\n",
                encoding="utf-8",
            )
            generated = run_script(model)

        names = [
            command["params"]["name"]
            for command in generated["commands"]
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(names, ["width"])
        self.assertNotIn("_x_position", names)

    def test_model_local_imports_do_not_create_pycache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "helper.py").write_text(
                "from scpf.core import Box\n"
                "class HelperBox:\n"
                "    size = 10.0\n"
                "    def build(self):\n"
                "        return Box(self.size, self.size, self.size)\n"
            )
            model = root / "model.py"
            model.write_text(
                "from helper import HelperBox\n"
                "class Wrapper:\n"
                "    size = 20.0\n"
                "    def build(self):\n"
                "        return Box(self.size, self.size, self.size)\n"
                "Wrapper()\n"
            )
            run_script(model)
            self.assertFalse((root / "__pycache__").exists())


    def test_plain_model_subclass_inherits_parameters_and_build(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Board:\n"
                "    width = 100.0\n"
                "    depth = 40.0\n"
                "    thickness = 12.0\n"
                "    corner_radius = 4.0\n"
                "    def build(self):\n"
                "        return Box(self.width, self.depth, self.thickness).fillet(\n"
                "            self.corner_radius, edges=Edges.VERTICAL)\n"
                "class BottomBoard(Board):\n"
                "    pass\n"
                "BottomBoard(width=868.0, depth=100.0)\n"
            )
            generated = run_script(file)
        params = [c["params"] for c in generated["commands"]
                  if c["command"] == "parameters.add"]
        self.assertEqual([p["name"] for p in params],
                         ["width", "depth", "thickness", "corner_radius"])
        self.assertEqual([p["expression"] for p in params],
                         ["868", "100", "12", "4"])
        fillet = next(c for c in generated["commands"]
                      if c["command"] == "solid.fillet")
        self.assertEqual(fillet["params"]["radius"], "corner_radius")


    def test_parameter_naming_distinguishes_model_build_and_constant_values(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Display:\n"
                "    opening_width = 844.0\n"
                "    panel_count = 5\n"
                "    _panel_pitch = 160.0\n"
                "    PANEL_DEPTH = 14.5\n"
                "    def build(self):\n"
                "        count = int(pv(self.panel_count))\n"
                "        assert count == 5\n"
                "        return Box(self.opening_width, self._panel_pitch, self.PANEL_DEPTH)\n"
                "Display()\n",
                encoding="utf-8",
            )
            with self.assertWarnsRegex(
                UserWarning,
                "parameter 'panel_count' has no native SolidCraft dependency",
            ):
                generated = run_script(file)

        names = [
            command["params"]["name"]
            for command in generated["commands"]
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(names, ["opening_width"])
        self.assertNotIn("_panel_pitch", names)
        self.assertNotIn("PANEL_DEPTH", names)

    def test_public_parameter_kept_in_native_geometry_does_not_warn(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Display:\n"
                "    opening_width = 844.0\n"
                "    def build(self):\n"
                "        return Box(self.opening_width, 100, 20)\n"
                "Display()\n",
                encoding="utf-8",
            )
            # No ModelParameterWarning should be emitted.
            import warnings
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                generated = run_script(file)

        self.assertFalse(
            any("no native SolidCraft dependency" in str(item.message)
                for item in caught)
        )
        self.assertEqual(
            [c["params"]["name"] for c in generated["commands"]
             if c["command"] == "parameters.add"],
            ["opening_width"],
        )



if __name__ == "__main__":
    unittest.main()
