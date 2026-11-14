"""Reusable model objects and native SolidCraft assembly command tests."""
from pathlib import Path
import tempfile
import unittest

from scpf.runner import run_script

ROOT = Path(__file__).resolve().parents[2]


class AssemblyTests(unittest.TestCase):
    def test_reusable_model_instances_compile_to_one_component_and_two_occurrences(self):
        commands = run_script(
            ROOT / "examples/components/scpf/model.py"
        )["commands"]

        self.assertEqual(
            [c["params"]["name"] for c in commands
             if c["command"] == "parameters.add"],
            ["Block_length", "Block_width", "Block_height"],
        )
        self.assertEqual(
            [c["params"]["name"] for c in commands
             if c["command"] == "component.create"],
            ["Block"],
        )
        copies = [c for c in commands if c["command"] == "occurrence.copy"]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]["params"]["component"], "Block")
        self.assertNotIn("translate", copies[0]["params"])
        placements = [c["params"] for c in commands if c["command"] == "occurrence.move"]
        self.assertEqual(placements[-1]["occurrence"], "Block:2")
        self.assertEqual(placements[-1]["translate"], [40.0, 0.0, 0.0])
        box = next(c for c in commands if c["command"] == "solid.box")
        self.assertIn("Block_length", str(box["params"]))
        self.assertIn("Block_width", str(box["params"]))

        joint = next(c for c in commands if c["command"] == "joint.create")
        self.assertEqual(joint["params"]["type"], "rigid")
        self.assertEqual(
            joint["params"]["a"],
            {"occurrence": "Block:1", "face": [20.0, 0.0, 5.0]},
        )
        self.assertEqual(
            joint["params"]["b"],
            {"occurrence": "Block:2", "face": [20.0, 0.0, 5.0]},
        )

    def test_copies_of_placed_occurrences_use_relative_native_offsets(self):
        """A copied occurrence inherits its source transform."""
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "sidewalls.py"
            script.write_text(
                "class SideWall:\n"
                "    def build(self):\n"
                "        return Box(15, 100, 362)\n"
                "class Cabinet:\n"
                "    def build(self):\n"
                "        left = SideWall().move(x=-429.5, y=25)\n"
                "        right = left.copy().move(x=859)\n"
                "        return (left + right).group('WoodBoxFrame')\n"
                "Cabinet()\n",
                encoding="utf-8",
            )
            commands = run_script(script)["commands"]
        copy = next(c["params"] for c in commands
                    if c["command"] == "occurrence.copy")
        self.assertEqual(copy["component"], "SideWall")
        self.assertNotIn("translate", copy)
        moves = [c["params"] for c in commands if c["command"] == "occurrence.move"]
        self.assertEqual([m["occurrence"] for m in moves], ["SideWall:1", "SideWall:2"])
        self.assertEqual(moves[0]["translate"], [-429.5, 25.0, 0.0])
        self.assertEqual(moves[1]["translate"], [429.5, 25.0, 0.0])

    def test_copy_resets_inherited_rotation_when_target_is_unrotated(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "rotated_source.py"
            script.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(20, 10, 2)\n"
                "class Cabinet:\n"
                "    def build(self):\n"
                "        first = Panel().move(x=-40).rotate(degrees=180)\n"
                "        right = first.copy().move(x=80).rotate(degrees=0)\n"
                "        return first + right\n"
                "Cabinet()\n",
                encoding="utf-8",
            )
            commands = run_script(script)["commands"]
        copy = next(c["params"] for c in commands
                    if c["command"] == "occurrence.copy")
        self.assertNotIn("translate", copy)
        commands_after_component = [c for c in commands
                                    if c["command"] in ("occurrence.copy", "occurrence.move")]
        self.assertEqual([c["command"] for c in commands_after_component],
                         ["occurrence.copy", "occurrence.move", "occurrence.move"])
        moves = [c["params"] for c in commands_after_component[1:]]
        self.assertEqual([m["translate"] for m in moves],
                         [[-40.0, 0.0, 0.0], [40.0, 0.0, 0.0]])
        self.assertEqual([m["angle"] for m in moves], ["180 deg", "0 deg"])
        self.assertTrue(all("matrix" not in m and "to" not in m for m in moves))

    def test_named_group_creates_real_nested_native_component(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "group.py"
            path.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(10, 2, 20)\n"
                "class Frame:\n"
                "    def build(self):\n"
                "        return Box(35, 10, 40)\n"
                "class Display:\n"
                "    def build(self):\n"
                "        left = Panel()\n"
                "        group = (left + left.copy().move(x=11)).group('HUB75Panels')\n"
                "        return group + Frame().move(y=20)\n"
                "Display()\n",
                encoding="utf-8",
            )
            commands = run_script(path)["commands"]
        created = [c["params"] for c in commands
                   if c["command"] == "component.create"]
        self.assertEqual([c["name"] for c in created],
                         ["HUB75Panels", "Panel", "Frame"])
        self.assertEqual(created[0]["activate"], False)
        self.assertTrue(created[0]["grounded"])
        self.assertEqual(created[1]["parent"], "HUB75Panels")
        self.assertFalse(created[1]["grounded"])
        self.assertNotIn("parent", created[2])
        copies = [c for c in commands if c["command"] == "occurrence.copy"]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]["params"]["component"], "Panel")

    def test_each_named_group_is_grounded_as_a_fixed_parent_frame(self):
        from scpf import Box, component
        from scpf.assembly import compile_assembly

        @component
        class LeftPart:
            def build(self):
                return Box(10, 10, 10)

        @component
        class RightPart:
            def build(self):
                return Box(12, 10, 10)

        left = LeftPart().group("LeftGroup")
        right = RightPart().group("RightGroup")
        commands = compile_assembly(left + right, "Grouped")["commands"]

        groups = [
            command["params"]
            for command in commands
            if command["command"] == "component.create"
            and command["params"]["name"] in {"LeftGroup", "RightGroup"}
        ]
        self.assertEqual(
            [(group["name"], group["grounded"]) for group in groups],
            [("LeftGroup", True), ("RightGroup", True)],
        )

    def test_group_name_conflicts_and_multi_parent_definitions_rejected(self):
        from scpf.core import Box
        from scpf.model_objects import ModelDefinition, ModelInstance
        from scpf.assembly import compile_assembly
        from scpf.compiler import ModelError
        panel = ModelInstance(ModelDefinition("Panel", (), Box(10, 2, 20)))
        with self.assertRaisesRegex(ValueError, "non-empty"):
            panel.group("")
        with self.assertRaisesRegex(ValueError, "multiple groups"):
            panel.group("One").group("Two")
        with self.assertRaisesRegex(ModelError, "multiple assembly parents"):
            compile_assembly(panel.group("A") + panel.copy(), "Display")
        with self.assertRaisesRegex(ModelError, "conflicts"):
            compile_assembly(panel.group("Panel"), "Display")

    def test_rotation_is_an_independent_occurrence_placement(self):
        from scpf.core import Box
        from scpf.model_objects import ModelDefinition, ModelInstance

        first = ModelInstance(ModelDefinition("Panel", (), Box(20, 10, 2)))
        second = first.copy().move(x=30).rotate(axis=(0, 0, 1), degrees=180)
        self.assertIs(first.definition, second.definition)
        self.assertIsNone(first.rotation)
        self.assertEqual(second.translation, (30, 0, 0))
        self.assertEqual(second.rotation, ((0.0, 0.0, 1.0), 180.0))
        self.assertIsNone(second.attachment)
        self.assertEqual(second.copy().rotation, second.rotation)
        self.assertEqual(second.move(x=10).translation, (40, 0, 0))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotation.py"
            path.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(20, 10, 2)\n"
                "class Display:\n"
                "    def build(self):\n"
                "        first = Panel()\n"
                "        return first + first.copy().move(x=30).rotate(degrees=180)\n"
                "Display()\n",
                encoding="utf-8",
            )
            commands = run_script(path)["commands"]

        self.assertEqual(len([c for c in commands if c["command"] == "component.create"]), 1)
        self.assertEqual(len([c for c in commands if c["command"] == "occurrence.copy"]), 1)
        rotated = [c["params"] for c in commands if c["command"] == "occurrence.move"]
        self.assertEqual(len(rotated), 1)
        self.assertEqual(rotated[0]["occurrence"], "Panel:2")
        self.assertNotIn("to", rotated[0])
        self.assertEqual(rotated[0]["translate"], [30.0, 0.0, 0.0])
        self.assertEqual(rotated[0]["axis"], [0.0, 0.0, 1.0])
        self.assertEqual(rotated[0]["angle"], "180 deg")
        self.assertNotIn("matrix", rotated[0])

    def test_named_axis_rotation_shorthand(self):
        from scpf.core import Box, X, Y, Z
        from scpf.model_objects import ModelDefinition, ModelInstance

        panel = ModelInstance(ModelDefinition("Panel", (), Box(20, 10, 2)))

        self.assertEqual(
            panel.rotate(X, 180).rotation,
            ((1.0, 0.0, 0.0), 180.0),
        )
        self.assertEqual(
            panel.rotate(Y, 90).rotation,
            ((0.0, 1.0, 0.0), 90.0),
        )
        self.assertEqual(
            panel.rotate(Z, -90).rotation,
            ((0.0, 0.0, 1.0), -90.0),
        )

        with self.assertRaisesRegex(ValueError, "X, Y or Z"):
            panel.rotate("Q", 90)

    def test_first_grounded_occurrence_can_have_absolute_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "root_rotation.py"
            path.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(20, 10, 2)\n"
                "class Display:\n"
                "    def build(self):\n"
                "        first = Panel().move(x=-50).rotate(degrees=180)\n"
                "        return first + first.copy().move(x=50).rotate(degrees=0)\n"
                "Display()\n", encoding="utf-8",
            )
            commands = run_script(path)["commands"]
        placements = [c["params"] for c in commands if c["command"] == "occurrence.move"]
        self.assertEqual(len(placements), 2)
        self.assertEqual(placements[0]["occurrence"], "Panel:1")
        self.assertTrue(placements[0]["move_grounded"])
        self.assertEqual(placements[0]["translate"], [-50.0, 0.0, 0.0])
        self.assertEqual(placements[1]["translate"], [0.0, 0.0, 0.0])
        self.assertEqual([m["angle"] for m in placements], ["180 deg", "0 deg"])

    def test_explicit_imported_component_factory(self):
        # The library's scpf/ source folder is a namespace root when the
        # test runner executes from the repository root. Import the module
        # directly here; the external-package public import is checked in CI.
        from scpf.runner import component
        from scpf.model_objects import ModelInstance

        class LibraryPanel:
            width = 20

            def build(self):
                from scpf.core import Box
                return Box(self.width, 10, 2)

        Panel = component(LibraryPanel)
        first = Panel()
        second = Panel().move(x=20)
        self.assertIsInstance(first, ModelInstance)
        self.assertIsInstance(second, ModelInstance)
        self.assertEqual(first.definition.key, second.definition.key)
        self.assertEqual(second.translation, (20, 0, 0))
        with self.assertRaisesRegex(TypeError, "model class"):
            component(42)

    def test_copies_start_at_origin_before_any_native_placement(self):
        """Five copies: only native SolidCraft operations, no matrix algebra."""
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "five.py"
            script.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(159.7, 319.71, 14.5)\n"
                "class Screen:\n"
                "    def build(self):\n"
                "        first = Panel().move(z=160).rotate(axis=(1,0,0), degrees=90)\n"
                "        return (first + first.copy().move(x=-320) +\n"
                "                first.copy().move(x=-160) +\n"
                "                first.copy().move(x=160) +\n"
                "                first.copy().move(x=320))\n"
                "Screen()\n",
                encoding="utf-8",
            )
            commands = run_script(script)["commands"]
        placements = [c for c in commands if c["command"] in (
            "occurrence.copy", "occurrence.move")]
        self.assertEqual([c["command"] for c in placements],
                         ["occurrence.copy"] * 4 + ["occurrence.move"] * 5)
        self.assertTrue(all(c["params"] == {"component": "Panel"}
                            for c in placements[:4]))
        self.assertEqual([c["params"]["translate"] for c in placements[4:]],
                         [[0.0, 0.0, 160.0], [-320.0, 0.0, 160.0],
                          [-160.0, 0.0, 160.0], [160.0, 0.0, 160.0],
                          [320.0, 0.0, 160.0]])
        self.assertTrue(all(c["params"]["axis"] == [1.,0.,0.]
                            and c["params"]["angle"] == "90 deg"
                            for c in placements[4:]))
        self.assertTrue(all("matrix" not in c["params"]
                            and "to" not in c["params"]
                            for c in placements))

    def test_rotation_rejects_undefined_and_nonfinite_axis_angle(self):
        from scpf.core import Box
        from scpf.model_objects import ModelDefinition, ModelInstance

        panel = ModelInstance(ModelDefinition("Panel", (), Box(2, 2, 1)))
        for kwargs in (
            {"axis": (0, 0, 0), "degrees": 90},
            {"axis": (0, 1), "degrees": 90},
            {"axis": (0, float("nan"), 1), "degrees": 90},
            {"axis": (0, 0, 1), "degrees": float("inf")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                panel.rotate(**kwargs)

    def test_component_attach_lowers_in_plane_offset_as_planar_joint(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, Box
        from scpf.model_objects import ModelDefinition, ModelInstance

        definition = ModelDefinition(
            "Block",
            (("length", 40.0), ("width", 30.0), ("height", 10.0)),
            Box(40, 30, 10),
        )
        left = ModelInstance(definition)
        right = ModelInstance(definition).attach(
            left,
            parent=Anchor.RIGHT,
            child=Anchor.LEFT,
            offset=(5, 7),
            gap=3,
            angle=15,
        )

        commands = compile_assembly(left + right, "OffsetAttach")["commands"]
        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "planar")
        self.assertEqual(joint["values"], [5, 7, 15])
        self.assertEqual(joint["offset"], 3)
        self.assertNotIn("angle", joint)

    def test_different_model_parameters_create_independent_component_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "model.py"
            file.write_text(
                "class Block:\n"
                "    length = 40.0\n"
                "    width = 30.0\n"
                "    height = 10.0\n"
                "    def build(self):\n"
                "        Box(self.length, self.width, self.height)\n"
                "class Pair:\n"
                "    def build(self):\n"
                "        left = Block(width=30.0)\n"
                "        right = Block(width=50.0).move(x=60.0)\n"
                "        left + right\n"
                "Pair()\n"
            )
            commands = run_script(file)["commands"]

        self.assertEqual(
            [c["params"]["name"] for c in commands
             if c["command"] == "component.create"],
            ["Block", "Block 2"],
        )
        self.assertFalse(any(c["command"] == "occurrence.copy" for c in commands))
        parameter_names = [
            c["params"]["name"] for c in commands
            if c["command"] == "parameters.add"
        ]
        self.assertEqual(
            parameter_names,
            [
                "Block_length", "Block_width", "Block_height",
                "Block_2_length", "Block_2_width", "Block_2_height",
            ],
        )


    def test_identical_material_is_created_once_across_components(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box
        from scpf.runner import component

        class Left:
            def build(self):
                return Box(10, 20, 30).with_material(
                    "WOOD", density_g_cm3=0.55, color="#CBA36B"
                )

        class Right:
            def build(self):
                return Box(10, 20, 30).with_material(
                    "WOOD", density_g_cm3=0.55, color="#CBA36B"
                )

        LeftPart = component(Left)
        RightPart = component(Right)
        commands = compile_assembly(
            LeftPart() + RightPart().move(x=20),
            "Frame",
        )["commands"]

        creates = [
            c["params"] for c in commands
            if c["command"] == "material.create"
        ]
        assigns = [
            c["params"] for c in commands
            if c["command"] == "material.assign"
        ]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0]["name"], "WOOD")
        self.assertEqual(len(assigns), 2)
        self.assertTrue(all(a["material"] == "WOOD" for a in assigns))

    def test_conflicting_shared_material_definition_is_rejected(self):
        from scpf.assembly import compile_assembly
        from scpf.compiler import ModelError
        from scpf.core import Box
        from scpf.runner import component

        class Left:
            def build(self):
                return Box(10, 20, 30).with_material(
                    "WOOD", density_g_cm3=0.55, color="#CBA36B"
                )

        class Right:
            def build(self):
                return Box(10, 20, 30).with_material(
                    "WOOD", density_g_cm3=0.55, color="#FFFFFF"
                )

        with self.assertRaisesRegex(ModelError, "defined differently"):
            compile_assembly(
                component(Left)() + component(Right)().move(x=20),
                "Frame",
            )

    def test_component_defaults_are_implicit_editable_parameters(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box
        from scpf.runner import component

        class Bracket:
            width = 24.0
            radius = 4.0
            chamfer = 2.0

            def build(self):
                return Box(
                    self.width,
                    self.radius + 20,
                    self.chamfer + 10,
                )

        BracketObject = component(Bracket)
        commands = compile_assembly(BracketObject(), "BracketAssembly")["commands"]
        names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(
            names,
            ["Bracket_width", "Bracket_radius", "Bracket_chamfer"],
        )

    def test_component_include_is_not_part_of_public_api(self):
        from scpf.runner import component

        class Bracket:
            width = 24.0

            def build(self):
                return Box(self.width, 20, 10)

        with self.assertRaises(TypeError):
            component(Bracket, include=("width",))

    def test_decorated_component_file_runs_as_standalone_root(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "component.py"
            script.write_text(
                "from scpf import component\n"
                "@component\n"
                "class Block:\n"
                "    width = 40.0\n"
                "    depth = 20.0\n"
                "    height = 10.0\n"
                "    def build(self):\n"
                "        return Box(self.width, self.depth, self.height)\n",
                encoding="utf-8",
            )
            commands = run_script(script)["commands"]

        self.assertFalse(
            any(command["command"] == "component.create" for command in commands)
        )
        self.assertEqual(
            [
                command["params"]["name"]
                for command in commands
                if command["command"] == "parameters.add"
            ],
            ["width", "depth", "height"],
        )
        self.assertTrue(
            any(command["command"] == "solid.box" for command in commands)
        )

    def test_decorated_component_is_reused_without_second_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "assembly.py"
            script.write_text(
                "from scpf import component\n"
                "@component\n"
                "class Block:\n"
                "    width = 40.0\n"
                "    def build(self):\n"
                "        return Box(self.width, 20, 10)\n"
                "class Pair:\n"
                "    def build(self):\n"
                "        first = Block()\n"
                "        return first + first.copy().move(x=50)\n"
                "Pair()\n",
                encoding="utf-8",
            )
            commands = run_script(script)["commands"]

        self.assertEqual(
            [
                command["params"]["name"]
                for command in commands
                if command["command"] == "component.create"
            ],
            ["Block"],
        )
        self.assertEqual(
            len([
                command for command in commands
                if command["command"] == "occurrence.copy"
                and command["params"]["component"] == "Block"
            ]),
            1,
        )


    def test_private_component_build_input_can_bind_parent_parameter(self):
        from scpf.assembly import compile_assembly
        from scpf import Sketch
        from scpf.core import Direction, Parameter, Polygon2D
        from scpf.runner import component

        class Bracket:
            width = 24.0
            _x_position = 0.0

            def build(self):
                x0 = self._x_position
                with Sketch(plane="XZ") as sketch:
                    Polygon2D([
                        (x0, 0),
                        (x0 + self.width, 0),
                        (x0 + self.width, 10),
                        (x0, 10),
                    ], plane="XZ", world=True)
                return sketch.extrude(10, direction=Direction.POSITIVE)

        BracketObject = component(Bracket)
        opening_width = Parameter("opening_width", 844.0)
        bracket = BracketObject(_x_position=opening_width / 2)

        self.assertNotIn(
            "_x_position",
            dict(bracket.definition.parameters),
        )
        self.assertEqual(
            dict(bracket.definition.external_parameters)["opening_width"],
            844.0,
        )
        self.assertIn(
            "opening_width",
            str(bracket.definition.shape.data),
        )

        commands = compile_assembly(bracket, "Display")["commands"]
        names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(names, ["opening_width", "Bracket_width"])
        self.assertNotIn("Bracket__x_position", names)

    def test_component_preserves_parent_parameter_dependency(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box, Parameter
        from scpf.runner import component

        class Panel:
            width = 100.0
            height = 20.0
            thickness = 2.0

            def build(self):
                return Box(self.width, self.thickness, self.height)

        PanelObject = component(Panel)
        parent_width = Parameter("opening_width", 844.0)
        instance = PanelObject(width=parent_width)

        self.assertNotIn("width", dict(instance.definition.parameters))
        self.assertEqual(
            dict(instance.definition.external_parameters)["opening_width"],
            844.0,
        )
        self.assertEqual(
            dict(instance.definition.input_bindings)["width"],
            "opening_width",
        )
        self.assertEqual(
            instance.definition.shape.data[0].name,
            "opening_width",
        )

        commands = compile_assembly(instance, "Display")["commands"]
        parameter_names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]
        self.assertIn("opening_width", parameter_names)
        self.assertNotIn("Panel_width", parameter_names)

    def test_shared_parent_parameter_is_added_once_for_multiple_components(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box, Parameter
        from scpf.runner import component

        class Strip:
            length = 100.0
            width = 12.0

            def build(self):
                return Box(self.length, self.width, 4)

        StripObject = component(Strip)
        opening_width = Parameter("opening_width", 844.0)

        horizontal = StripObject(length=opening_width, width=12.0)
        second = StripObject(length=opening_width, width=15.0).move(y=20)

        commands = compile_assembly(horizontal + second, "Frame")["commands"]
        parameter_names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]

        self.assertEqual(parameter_names.count("opening_width"), 1)
        self.assertNotIn("Strip_length", parameter_names)
        self.assertNotIn("Strip_2_length", parameter_names)
        self.assertIn("Strip_width", parameter_names)
        self.assertIn("Strip_2_width", parameter_names)

    def test_parent_expression_remains_an_expression_in_child_geometry(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box, Parameter
        from scpf.runner import component

        class Board:
            width = 100.0
            thickness = 12.0

            def build(self):
                return Box(self.width, 50, self.thickness)

        BoardObject = component(Board)
        opening_width = Parameter("opening_width", 844.0)
        frame_wood_thickness = Parameter("frame_wood_thickness", 12.0)
        outer_width = opening_width + 2 * frame_wood_thickness

        board = BoardObject(width=outer_width)
        commands = compile_assembly(board, "Frame")["commands"]

        parameter_names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(parameter_names.count("opening_width"), 1)
        self.assertEqual(parameter_names.count("frame_wood_thickness"), 1)
        self.assertNotIn("Board_width", parameter_names)

        box = next(
            command for command in commands
            if command["command"] == "solid.box"
        )
        self.assertIn("opening_width", str(box["params"]))
        self.assertIn("frame_wood_thickness", str(box["params"]))

    def test_named_component_objects_resolve_directly_from_assembly(self):
        from scpf.core import Box
        from scpf.runner import component

        class Board:
            width = 100.0

            def build(self):
                return Box(self.width, 20, 10)

        BoardObject = component(Board)
        roof = BoardObject(name="roof", width=120)
        bottom = BoardObject(name="bottom", width=100)
        frame = roof + bottom

        self.assertIs(frame.roof, roof)
        self.assertIs(frame.bottom, bottom)
        self.assertIs(frame.resolve("roof"), roof)

        copy = roof.copy()
        self.assertIsNone(copy.name)

        with self.assertRaisesRegex(ValueError, "object names must be unique"):
            _ = roof + BoardObject(name="roof")

    def test_plain_assembly_accepts_non_parametric_object_reference_input(self):
        from scpf.core import Box, Parameter
        from scpf.runner import assembly, component
        from scpf.model_objects import Assembly

        class FramePart:
            def build(self):
                return Box(40, 20, 10)

        FrameObject = component(FramePart)
        frame = FrameObject()

        @assembly
        class Brackets:
            wood_frame = None
            spacing = 30.0

            def build(self):
                self.assert_reference = self.wood_frame
                marker = FrameObject().move(x=self.spacing)
                return self.wood_frame + marker

        brackets = Brackets(
            wood_frame=frame,
            spacing=Parameter("spacing", 50.0),
        )

        self.assertIsInstance(brackets, Assembly)
        self.assertEqual(len(brackets.instances), 2)
        self.assertIs(brackets.instances[0], frame)
        self.assertEqual(brackets.instances[1].translation[0].name, "spacing")
        self.assertEqual(brackets.instances[1].translation[1:], (0, 0))

    def test_imported_assembly_class_uses_object_syntax(self):
        from scpf.core import Box, Parameter
        from scpf.runner import assembly, component
        from scpf.model_objects import Assembly

        class Panel:
            width = 100.0
            height = 20.0
            thickness = 2.0

            def build(self):
                return Box(self.width, self.thickness, self.height)

        PanelObject = component(Panel)

        class PanelRow:
            width = 100.0
            pitch = 110.0

            def build(self):
                left = PanelObject(width=self.width)
                right = left.copy().move(x=self.pitch)
                return (left + right).group("Panels")

        PanelRowObject = assembly(PanelRow)
        row = PanelRowObject(
            width=Parameter("panel_width", 160.0),
            pitch=Parameter("panel_pitch", 170.0),
        )

        self.assertIsInstance(row, Assembly)
        self.assertEqual(len(row.instances), 2)
        self.assertEqual(row.instances[1].translation[0].name, "panel_pitch")
        self.assertEqual(row.instances[1].translation[1:], (0, 0))
        self.assertNotIn(
            "width",
            dict(row.instances[0].definition.parameters),
        )
        self.assertEqual(
            dict(row.instances[0].definition.external_parameters)["panel_width"],
            160.0,
        )


    def test_symbolic_move_lowers_to_parametric_placement_joint(self):
        import warnings

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parametric_move.py"
            path.write_text(
                "class Panel:\n"
                "    depth = 12.0\n"
                "    def build(self):\n"
                "        return Box(40, self.depth, 20)\n"
                "class Display:\n"
                "    depth = 12.0\n"
                "    def build(self):\n"
                "        return Panel(depth=self.depth).move(y=half(self.depth))\n"
                "Display()\n",
                encoding="utf-8",
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                document = run_script(path)

        self.assertFalse([
            item for item in caught
            if "parameter 'depth'" in str(item.message)
        ])
        self.assertFalse(any(
            command["command"] == "occurrence.move"
            for command in document["commands"]
        ))
        placement = next(
            command["params"]
            for command in document["commands"]
            if command["command"] == "joint.create"
            and command["params"]["name"] == "Place Panel:1"
        )
        self.assertEqual(placement["type"], "planar")
        self.assertEqual(
            placement["a"],
            {
                "occurrence": "root",
                "frame": {
                    "origin": [0.0, 0.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                    "x": [1.0, 0.0, 0.0],
                },
            },
        )
        self.assertEqual(placement["values"], [0, "depth / 2", 0.0])
        self.assertEqual(placement["offset"], 0)
        self.assertTrue(placement["flip"])
        names = [
            command["params"]["name"]
            for command in document["commands"]
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(names, ["depth"])

    def test_symbolic_move_adds_placement_only_parameter(self):
        import warnings

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "placement_only.py"
            path.write_text(
                "class Panel:\n"
                "    def build(self):\n"
                "        return Box(40, 12, 20)\n"
                "class Display:\n"
                "    offset = 30.0\n"
                "    def build(self):\n"
                "        return Panel().move(x=self.offset)\n"
                "Display()\n",
                encoding="utf-8",
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                document = run_script(path)

        self.assertFalse([
            item for item in caught
            if "parameter 'offset'" in str(item.message)
        ])
        parameter = next(
            command["params"]
            for command in document["commands"]
            if command["command"] == "parameters.add"
            and command["params"]["name"] == "offset"
        )
        self.assertEqual(parameter["expression"], "30 mm")
        placement = next(
            command["params"]
            for command in document["commands"]
            if command["command"] == "joint.create"
            and command["params"]["name"] == "Place Panel:1"
        )
        self.assertEqual(placement["values"], ["offset", 0, 0.0])
        self.assertEqual(placement["offset"], 0)

    def test_symbolic_move_with_rotation_rotates_first_then_places(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotated_parametric_move.py"
            path.write_text(
                "class Strip:\n"
                "    def build(self):\n"
                "        return Box(40, 12, 4)\n"
                "class Frame:\n"
                "    height = 100.0\n"
                "    def build(self):\n"
                "        return Strip().rotate(Y, 90).move(z=half(self.height))\n"
                "Frame()\n",
                encoding="utf-8",
            )
            document = run_script(path)

        move = next(
            command["params"]
            for command in document["commands"]
            if command["command"] == "occurrence.move"
        )
        self.assertEqual(move["translate"], [0.0, 0.0, 0.0])
        self.assertEqual(move["axis"], [0.0, 1.0, 0.0])
        self.assertEqual(move["angle"], "90 deg")

        placement = next(
            command["params"]
            for command in document["commands"]
            if command["command"] == "joint.create"
            and command["params"]["name"] == "Place Strip:1"
        )
        self.assertEqual(placement["offset"], "height / 2")

    def test_attachment_uses_numeric_seed_not_second_parametric_placement(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, Box, Parameter
        from scpf.runner import component

        class Panel:
            def build(self):
                return Box(40, 12, 20)

        PanelObject = component(Panel)
        station = Parameter("station", 100.0)
        parent = PanelObject().move(x=station)
        child = PanelObject().attach(
            parent,
            parent=Anchor.RIGHT,
            child=Anchor.LEFT,
        )

        commands = compile_assembly(parent + child, "Pair")["commands"]

        placements = [
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
            and command["params"]["name"].startswith("Place ")
        ]
        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0]["values"][0], "station")

        child_move = next(
            command["params"]
            for command in commands
            if command["command"] == "occurrence.move"
            and command["params"]["occurrence"] == "Panel:2"
        )
        self.assertTrue(
            all(isinstance(value, (int, float)) for value in child_move["translate"])
        )

        attachment = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
            and command["params"]["name"].startswith("Attach Panel:2")
        )
        self.assertEqual(attachment["type"], "rigid")

    def test_parent_parameter_binding_reuses_existing_name_without_child_duplicate(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box, Edges, Parameter
        from scpf.runner import component

        class Bracket:
            bracket_width = 24.0
            inside_corner_radius = 4.0

            def build(self):
                return Box(self.bracket_width, 40, 40).fillet(
                    self.inside_corner_radius,
                    edges=Edges.VERTICAL,
                )

        BracketObject = component(Bracket)
        shared = Parameter("corner_radius", 5.0)
        commands = compile_assembly(
            BracketObject(inside_corner_radius=shared),
            "Display",
        )["commands"]

        parameter_names = [
            command["params"]["name"]
            for command in commands
            if command["command"] == "parameters.add"
        ]
        self.assertEqual(
            parameter_names,
            ["Bracket_bracket_width", "corner_radius"],
        )
        self.assertNotIn("Bracket_inside_corner_radius", parameter_names)

        fillet = next(
            command["params"]
            for command in commands
            if command["command"] == "solid.fillet"
        )
        self.assertEqual(fillet["radius"], "corner_radius")


    def test_xz_rectangular_component_uses_standard_corner_anchor(self):
        commands = run_script(
            ROOT / "examples/xz-anchor/scpf/model.py"
        )["commands"]

        joints = [
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        ]
        self.assertEqual(len(joints), 2)
        self.assertEqual(
            joints[0]["a"],
            {
                "occurrence": "Board:1",
                "edge": [20.0, 0.0, 10.0],
                "on": [0.0, 0.0, 10.0],
                "corner": [20.0, 0.0, 20.0],
            },
        )
        self.assertEqual(
            joints[1]["a"],
            {
                "occurrence": "Board:1",
                "edge": [-20.0, 0.0, 10.0],
                "on": [0.0, 0.0, 10.0],
                "corner": [-20.0, 0.0, 20.0],
            },
        )
        self.assertEqual(
            [joint["b"]["occurrence"] for joint in joints],
            ["Marker:1", "Marker:2"],
        )
        self.assertEqual(
            joints[0]["b"],
            {
                "occurrence": "Marker:1",
                "point": [20.0, 0.0, 20.0],
                "z": [0.0, 1.0, 0.0],
                "x": [-1.0, 0.0, 0.0],
            },
        )
        self.assertEqual(
            joints[1]["b"],
            {
                "occurrence": "Marker:2",
                "point": [-20.0, 0.0, 20.0],
                "z": [0.0, 1.0, 0.0],
                "x": [0.0, 0.0, -1.0],
            },
        )

    def test_anchor_frame_accepts_named_axis_directions(self):
        from scpf import Anchor, AnchorFrame

        frame = AnchorFrame(
            origin=(10, 25, 0),
            z=Anchor.RIGHT,
            x=Anchor.UP,
        )

        self.assertEqual(frame.origin, (10.0, 25.0, 0.0))
        self.assertEqual(frame.z, (1.0, 0.0, 0.0))
        self.assertEqual(frame.x, (0.0, 0.0, 1.0))

    def test_unrotated_custom_anchors_are_inlined_per_occurrence(self):
        from scpf.assembly import compile_assembly
        from scpf.core import AnchorFrame, Box
        from scpf.runner import component

        class Base:
            def anchors(self):
                return {
                    "front_mount": AnchorFrame(origin=(0, 0, 0)),
                    "rear_mount": AnchorFrame(origin=(0, 0, 0), z=(0, 0, -1)),
                }

            def build(self):
                return Box(20, 20, 10)

        class Bracket:
            def anchors(self):
                return {
                    "front_mount": AnchorFrame(origin=(0, 0, 0)),
                    "rear_mount": AnchorFrame(origin=(0, 0, 0), z=(0, 0, -1)),
                }

            def build(self):
                return Box(10, 10, 10)

        BaseObject = component(Base)
        BracketObject = component(Bracket)

        base = BaseObject()
        front = BracketObject().attach(
            base,
            parent="front_mount",
            child="front_mount",
        )
        rear = BracketObject().attach(
            base,
            parent="rear_mount",
            child="rear_mount",
        )

        commands = compile_assembly(base + front + rear, "SelectiveAnchors")["commands"]
        self.assertFalse(
            any(command["command"] == "joint.origin" for command in commands)
        )

        joints = [
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        ]
        self.assertEqual(len(joints), 2)
        self.assertEqual(
            joints[0]["a"],
            {
                "occurrence": "Base:1",
                "point": [0.0, 0.0, 0.0],
                "z": [0.0, 0.0, 1.0],
                "x": [1.0, 0.0, 0.0],
            },
        )
        self.assertEqual(
            joints[0]["b"],
            {
                "occurrence": "Bracket:1",
                "point": [0.0, 0.0, 0.0],
                "z": [0.0, 0.0, 1.0],
                "x": [1.0, 0.0, 0.0],
            },
        )
        self.assertEqual(joints[1]["a"]["z"], [0.0, 0.0, -1.0])
        self.assertEqual(joints[1]["b"]["z"], [0.0, 0.0, -1.0])

    def test_assembly_can_own_named_attachment_anchor(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, AnchorTopology, Box
        from scpf.runner import component

        @component
        class Block:
            def build(self):
                return Box(20, 20, 10)

        left = Block(name="left")
        right = Block(name="right").move(x=40)
        topology = AnchorTopology(
            edge=(-10, 0, 5),
            on=(0, 0, 5),
            corner=(-10, 0, 10),
            z=(0, 0, -1),
            x=(1, 0, 0),
        )
        frame = (left + right).with_anchor(
            "top_left",
            left,
            topology,
            offset=(5, 0),
        )

        anchor = frame.anchor("top_left")
        self.assertIs(anchor.target, left)
        self.assertIs(anchor.reference, topology)
        self.assertEqual(anchor.offset, (5, 0))

        marker = Block().attach(
            anchor.target,
            parent=anchor.reference,
            child=Anchor.LEFT,
        )
        commands = compile_assembly(frame + marker, "AssemblyAnchor")["commands"]
        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["a"]["occurrence"], "Block:1")
        self.assertEqual(joint["a"]["edge"], [-10.0, 0.0, 5.0])
        self.assertEqual(joint["a"]["corner"], [-10.0, 0.0, 10.0])

    def test_group_preserves_assembly_anchor_target(self):
        from scpf.core import AnchorTopology, Box
        from scpf.runner import component

        @component
        class Block:
            def build(self):
                return Box(20, 20, 10)

        left = Block(name="left")
        frame = (left + Block(name="right")).with_anchor(
            "left_edge",
            left,
            AnchorTopology(edge=(-10, 0, 5), on=(0, 0, 5)),
        )
        grouped = frame.group("Frame")
        anchor = grouped.anchor("left_edge")

        self.assertEqual(anchor.target.name, "left")
        self.assertEqual(anchor.target.group_name, "Frame")
        self.assertIs(anchor.target, grouped.left)

    def test_named_topology_anchor_is_inlined_as_edge_reference(self):
        from scpf.assembly import compile_assembly
        from scpf.core import AnchorFrame, AnchorTopology, Box
        from scpf.runner import component

        @component
        class Board:
            def anchors(self):
                return {
                    "front_tangent": AnchorTopology(
                        edge=(-20, 0, 5),
                        on=(-20, 10, 10),
                        corner=(-20, 0, 5),
                        z=(0, 1, 0),
                        x=(0, 0, 1),
                    )
                }

            def build(self):
                return Box(40, 20, 20)

        @component
        class Marker:
            def build(self):
                return Box(10, 10, 10)

        board = Board()
        marker = Marker().attach(
            board,
            parent="front_tangent",
            child=AnchorFrame(),
        )

        commands = compile_assembly(board + marker, "TopologyAnchor")["commands"]
        self.assertFalse(
            any(command["command"] == "joint.origin" for command in commands)
        )
        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(
            joint["a"],
            {
                "occurrence": "Board:1",
                "edge": [-20.0, 0.0, 5.0],
                "on": [-20.0, 10.0, 10.0],
                "corner": [-20.0, 0.0, 5.0],
                "z": [0.0, 1.0, 0.0],
                "x": [0.0, 0.0, 1.0],
            },
        )

    def test_direct_topology_anchor_is_inlined(self):
        from scpf.assembly import compile_assembly
        from scpf.core import AnchorFrame, AnchorTopology, Box
        from scpf.runner import component

        @component
        class Block:
            def build(self):
                return Box(20, 20, 10)

        base = Block()
        child = Block().attach(
            base,
            parent=AnchorTopology(
                edge=(10, 0, 5),
                on=(0, 0, 5),
                corner=(10, 0, 0),
                z=(0, 0, -1),
                x=(-1, 0, 0),
            ),
            child=AnchorFrame(),
        )
        joint = next(
            command["params"]
            for command in compile_assembly(base + child, "DirectTopology")["commands"]
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["a"]["edge"], [10.0, 0.0, 5.0])
        self.assertEqual(joint["a"]["corner"], [10.0, 0.0, 0.0])
        self.assertEqual(joint["a"]["z"], [0.0, 0.0, -1.0])

    def test_named_topology_anchor_rejects_rotated_occurrence(self):
        from scpf.assembly import compile_assembly
        from scpf.compiler import ModelError
        from scpf.core import Anchor, AnchorTopology, Axis, Box
        from scpf.runner import component

        @component
        class Board:
            def anchors(self):
                return {
                    "edge_mount": AnchorTopology(
                        edge=(10, 0, 5),
                        on=(0, 0, 5),
                    )
                }

            def build(self):
                return Box(20, 20, 10)

        board = Board().rotate(Axis.Z, 90)
        child = Board().attach(board, parent="edge_mount", child=Anchor.LEFT)

        with self.assertRaisesRegex(
            ModelError, "AnchorTopology.*rotated"
        ):
            compile_assembly(board + child, "RotatedTopologyAnchor")


    def test_direct_anchor_frame_rigid_attach_fixes_mating_angle(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, AnchorFrame, Box
        from scpf.runner import component

        @component
        class Base:
            def build(self):
                return Box(40, 30, 20)

        @component
        class Bracket:
            def build(self):
                return Box(10, 4, 10)

        base = Base()
        child_frame = AnchorFrame(
            origin=(0, 0, 0),
            z=Anchor.FRONT,
            x=Anchor.RIGHT,
        )
        bracket = Bracket().attach(
            base,
            parent=Anchor.FRONT_TOP_LEFT,
            child=child_frame,
        )

        commands = compile_assembly(base + bracket, "RigidFrame")["commands"]
        joint = next(
            row["params"]
            for row in commands
            if row["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "rigid")
        self.assertEqual(joint["angle"], 0.0)

    def test_direct_anchor_frame_planar_attach_fixes_mating_angle(self):
        from scpf.assembly import compile_assembly
        from scpf.core import AnchorFrame, Box
        from scpf.runner import component

        @component
        class Base:
            def build(self):
                return Box(40, 30, 20)

        @component
        class Marker:
            def build(self):
                return Box(10, 10, 10)

        parent = AnchorFrame(
            origin=(0, 0, 0),
            z=(0, 0, -1),
            x=(0, -1, 0),
        )
        child = AnchorFrame(
            origin=(0, 0, 0),
            z=(0, 0, 1),
            x=(0, 1, 0),
        )
        base = Base()
        marker = Marker().attach(
            base,
            parent=parent,
            child=child,
            offset=(10, 20),
        )

        commands = compile_assembly(base + marker, "PlanarFrames")["commands"]
        joint = next(
            row["params"]
            for row in commands
            if row["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "planar")
        self.assertEqual(joint["values"], [10.0, 20.0, 0.0])
        self.assertEqual(joint["angle"], 0.0)

    def test_direct_anchor_frame_attachment_is_inlined(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, AnchorFrame, Box
        from scpf.runner import component

        @component
        class Base:
            def build(self):
                return Box(40, 40, 40)

        @component
        class Bracket:
            def build(self):
                return Box(10, 10, 10)

        base = Base()
        mount = AnchorFrame(
            origin=(0, 0, -5),
            z=(0, 1, 0),
            x=(0, 0, -1),
        )
        bracket = Bracket().attach(
            base,
            parent=Anchor.FRONT_TOP_RIGHT,
            child=mount,
        )

        commands = compile_assembly(base + bracket, "DirectFrame")["commands"]
        self.assertFalse(
            any(command["command"] == "joint.origin" for command in commands)
        )
        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(
            joint["b"],
            {
                "occurrence": "Bracket:1",
                "point": [20.0, -20.0, 40.0],
                "z": [0.0, 1.0, 0.0],
                "x": [0.0, 0.0, -1.0],
            },
        )

    def test_direct_anchor_frame_rejects_rotated_occurrence(self):
        from scpf.assembly import compile_assembly
        from scpf.compiler import ModelError
        from scpf.core import Anchor, AnchorFrame, Axis, Box
        from scpf.runner import component

        @component
        class Block:
            def build(self):
                return Box(20, 20, 20)

        base = Block()
        child = Block().rotate(Axis.Z, 90).attach(
            base,
            parent=Anchor.RIGHT,
            child=AnchorFrame(),
        )

        with self.assertRaisesRegex(
            ModelError, "direct AnchorFrame attachments.*rotated"
        ):
            compile_assembly(base + child, "RotatedDirectFrame")


    def test_generated_joint_glyphs_are_hidden_after_assembly_compile(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, Box
        from scpf.runner import component

        class Block:
            def build(self):
                return Box(20, 20, 10)

        BlockObject = component(Block)
        base = BlockObject()
        child = BlockObject().attach(
            base,
            parent=Anchor.RIGHT,
            child=Anchor.LEFT,
        )

        commands = compile_assembly(base + child, "HiddenJointGlyphs")["commands"]
        self.assertEqual(
            commands[-1],
            {
                "command": "browser.visibility",
                "params": {"folder": "joints", "visible": False},
            },
        )
        self.assertTrue(
            any(command["command"] == "joint.create" for command in commands[:-1])
        )

        no_joint_commands = compile_assembly(BlockObject(), "NoJoints")["commands"]
        self.assertFalse(
            any(command["command"] == "browser.visibility"
                for command in no_joint_commands)
        )

    def test_rotated_custom_anchor_materializes_before_rotation(self):
        commands = run_script(
            ROOT / "examples/custom-anchor/scpf/model.py"
        )["commands"]

        origins = [
            command["params"]
            for command in commands
            if command["command"] == "joint.origin"
        ]
        self.assertEqual(
            origins,
            [
                {
                    "name": "Arm:1.tip",
                    "occurrence": "Arm:1",
                    "frame": {
                        "origin": [20.0, 0.0, 5.0],
                        "z": [1.0, 0.0, 0.0],
                        "x": [0.0, 0.0, 1.0],
                    },
                },
            ],
        )

        arm_origin_index = next(
            i for i, command in enumerate(commands)
            if command["command"] == "joint.origin"
            and command["params"]["name"] == "Arm:1.tip"
        )
        arm_move_index = next(
            i for i, command in enumerate(commands)
            if command["command"] == "occurrence.move"
            and command["params"]["occurrence"] == "Arm:1"
        )
        self.assertLess(arm_origin_index, arm_move_index)

        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["a"], "Arm:1.tip")
        self.assertEqual(
            joint["b"],
            {
                "occurrence": "Marker:1",
                "point": [20.0, 0.0, 5.0],
                "z": [-1.0, 0.0, 0.0],
                "x": [0.0, 0.0, 1.0],
            },
        )

    def test_composed_directions_are_valid_assembly_anchors(self):
        from scpf import Anchor, BOTTOM, FRONT, LEFT, TOP, Box
        from scpf.assembly import compile_assembly
        from scpf.runner import component

        @component
        class Block:
            def build(self):
                return Box(40, 30, 10)

        base = Block(name="base")
        child = Block(name="child")
        child = child.attach(
            base,
            parent=FRONT + TOP + LEFT,
            child=FRONT + BOTTOM + LEFT,
        )

        self.assertIs(child.attachment.parent, Anchor.FRONT_TOP_LEFT)
        self.assertIs(child.attachment.child, Anchor.FRONT_BOTTOM_LEFT)

        commands = compile_assembly(base + child, "DirectionalAttach")["commands"]
        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "rigid")
        self.assertIn("corner", joint["a"])
        self.assertEqual(joint["b"]["point"], [-20.0, -15.0, 10.0])
        self.assertEqual(joint["b"]["z"], [0.0, -1.0, 0.0])

    def test_corner_anchor_compiles_to_native_edge_and_corner_origins(self):
        commands = run_script(
            ROOT / "examples/corner-anchor/scpf/model.py"
        )["commands"]

        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "rigid")
        self.assertEqual(
            joint["a"],
            {
                "occurrence": "Base:1",
                "edge": [20.0, -15.0, 10.0],
                "on": [0.0, -15.0, 10.0],
                "corner": [20.0, -15.0, 20.0],
            },
        )
        self.assertEqual(
            joint["b"],
            {
                "occurrence": "Marker:1",
                "point": [20.0, -15.0, 20.0],
                "z": [0.0, 1.0, 0.0],
                "x": [-1.0, 0.0, 0.0],
            },
        )

    def test_as_built_attach_keeps_current_occurrence_placement(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Box
        from scpf.runner import component

        class Block:
            def build(self):
                return Box(20, 20, 10)

        BlockObject = component(Block)
        base = BlockObject()
        child = BlockObject().move(x=40).attach(
            base,
            as_built=True,
        )

        commands = compile_assembly(base + child, "AsBuiltAttach")["commands"]

        move = next(
            command["params"]
            for command in commands
            if command["command"] == "occurrence.move"
            and command["params"]["occurrence"] == "Block:2"
        )
        self.assertEqual(move["translate"], [40.0, 0.0, 0.0])

        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.as_built"
        )
        self.assertEqual(joint["type"], "rigid")
        self.assertEqual(joint["a"], "Block:1")
        self.assertEqual(joint["b"], "Block:2")

    def test_attach_angle_is_emitted_as_native_joint_turn(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, Box
        from scpf.runner import component

        class Block:
            def build(self):
                return Box(20, 20, 10)

        BlockObject = component(Block)
        base = BlockObject()
        zero = BlockObject().attach(
            base,
            parent=Anchor.RIGHT,
            child=Anchor.LEFT,
            angle=0,
        )
        quarter = BlockObject().attach(
            base,
            parent=Anchor.TOP,
            child=Anchor.BOTTOM,
            angle=90,
        )

        commands = compile_assembly(
            base + zero + quarter,
            "AngleAttach",
        )["commands"]
        joints = [
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        ]
        self.assertEqual([joint["type"] for joint in joints], ["rigid", "rigid"])
        self.assertEqual([joint["angle"] for joint in joints], [0, 90])

    def test_attach_seed_includes_current_offset_and_gap_values(self):
        from scpf.core import Anchor, Box, Parameter
        from scpf.model_objects import ModelDefinition, ModelInstance

        definition = ModelDefinition("Block", (), Box(40, 30, 10))
        base = ModelInstance(definition)
        gap = Parameter("gap", 5)

        child = ModelInstance(definition).attach(
            base,
            parent=Anchor.TOP,
            child=Anchor.BOTTOM,
            offset=(10, -2),
            gap=gap,
        )

        self.assertEqual(child.translation, (10.0, -2.0, 15.0))
        self.assertIs(child.attachment.gap, gap)
        self.assertEqual(child.attachment.offset, (10, -2))

    def test_parametric_attach_keeps_in_plane_offset_expression(self):
        from scpf.assembly import compile_assembly
        from scpf.core import Anchor, Box, Parameter
        from scpf.model_objects import ModelDefinition, ModelInstance

        definition = ModelDefinition("Block", (), Box(40, 30, 10))
        left = ModelInstance(definition)
        wood = Parameter("wood_thickness", 18)
        right = ModelInstance(definition).attach(
            left,
            parent=Anchor.RIGHT,
            child=Anchor.LEFT,
            offset=(0, -wood + 12),
        )
        self.assertEqual(right.translation, (40.0, 0.0, -6.0))

        commands = compile_assembly(left + right, "ParametricOffset")["commands"]
        parameter = next(
            command["params"]
            for command in commands
            if command["command"] == "parameters.add"
            and command["params"]["name"] == "wood_thickness"
        )
        self.assertEqual(parameter["expression"], "18 mm")

        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "planar")
        self.assertEqual(
            joint["values"],
            [0, "-(wood_thickness) + 12 mm", 0.0],
        )


    def test_parametric_attach_keeps_gap_as_native_joint_expression(self):
        commands = run_script(
            ROOT / "examples/parametric-attach/scpf/model.py"
        )["commands"]

        gap = next(
            command["params"]
            for command in commands
            if command["command"] == "parameters.add"
            and command["params"]["name"] == "gap"
        )
        self.assertEqual(gap["expression"], "10 mm")

        joint = next(
            command["params"]
            for command in commands
            if command["command"] == "joint.create"
        )
        self.assertEqual(joint["type"], "rigid")
        self.assertEqual(joint["offset"], "gap")



if __name__ == "__main__":
    unittest.main()
