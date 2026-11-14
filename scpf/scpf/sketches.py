"""Native SolidCraft sketch construction for primitive CAD profiles.

Each supported base shape returns its command list plus simple shape metadata.
Feature operations (Hole, Fillet, join, cut) are handled separately.
"""
from math import isfinite
from .core import Shape, command_value, half, pv
from .placement import _base_rectangle


def _combine_dimension(a, b):
    """Preserve native expressions when adding an offset to a parameter."""
    if isinstance(a, (int, float)) and a == 0:
        return b
    if isinstance(b, (int, float)) and b == 0:
        return a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + b
    return f"({command_value(a)}) + ({command_value(b)})"

from .compiler import ModelError, _command, _require_positive
from .csg import _half

def compile_base(shape, name):
    """Create a native editable base body, regardless of example/model name."""
    if shape.kind in ("box", "placed_box"):
        if shape.kind == "box":
            length, width, height = shape.data
            origin = (-half(length), -half(width), 0)
            command_corner = (
                _half(length, True),
                _half(width, True),
                0,
            )
        else:
            (length, width), origin, height = _base_rectangle(shape)
            command_corner = tuple(command_value(value) for value in origin)

        _require_positive(length, "box length")
        _require_positive(width, "box width")
        _require_positive(height, "box height")
        # Native 3D primitives must not synthesize a 2D sketch.
        steps = [
            _command(
                "solid.box",
                length=command_value(length),
                width=command_value(width),
                height=command_value(height),
                corner=list(command_corner),
                body_name=name,
            ),
        ]
        return steps, {
            "profile": "rectangle",
            "primitive": "box",
            "width": length,
            "depth": width,
            "thickness": height,
            "origin": origin,
        }

    if shape.kind == "sketch_base_extrusion":
        sketch_name, plane, origin, plane_offset, profiles, distance, direction = shape.data
        _require_positive(distance, "sketch extrusion distance")
        if plane not in ("XY", "XZ", "YZ"):
            raise ModelError("standalone Sketch requires an XY, XZ or YZ plane")
        if len(profiles) != 1:
            raise ModelError("standalone Sketch currently requires exactly one profile")
        profile, (ox, oy) = profiles[0]
        if origin is not None:
            raise ModelError("standalone Sketch origin is not supported yet")
        sketch_params = {"plane": plane, "name": sketch_name}
        if plane_offset is not None:
            sketch_params["offset"] = command_value(plane_offset)
        sketch = [_command("sketch.create", **sketch_params)]
        if profile.kind == "rectangle":
            width, depth = profile.data
            _require_positive(width, "rectangle width")
            _require_positive(depth, "rectangle depth")
            sketch.append(_command("sketch.rectangle.two_point",
                p0=[command_value(ox), command_value(oy)],
                p1=[command_value(_combine_dimension(ox, width)),
                    command_value(_combine_dimension(oy, depth))]))
            meta = {"profile": "rectangle", "width": width, "depth": depth,
                    "thickness": distance, "origin": (ox, oy, 0)}
        elif profile.kind == "circle":
            (diameter,) = profile.data
            _require_positive(diameter, "circle diameter")
            sketch.append(_command("sketch.circle.center",
                center=[command_value(ox), command_value(oy)],
                diameter=command_value(diameter)))
            meta = {"profile": "circle", "thickness": distance}
        elif profile.kind == "polygon":
            points, profile_plane, ids = profile.data
            if profile_plane != plane:
                raise ModelError("Polygon2D plane must match Sketch plane")
            if pv(ox) or pv(oy):
                raise ModelError("standalone Polygon2D offset is not supported yet")
            concrete = [tuple(pv(v) for v in point) for point in points]
            if not all(isfinite(v) for point in concrete for v in point):
                raise ModelError("non-finite polygon coordinate")
            if len(set(concrete)) != len(concrete):
                raise ModelError("duplicate polygon vertices")
            if any(a == b for a, b in zip(concrete, concrete[1:] + concrete[:1])):
                raise ModelError("zero-length polygon edge")
            sketch.append(_command("sketch.line",
                points=[[command_value(v) for v in point] for point in points],
                closed=True, ids=list(ids) if ids is not None else
                [chr(ord("a") + i) for i in range(len(points))]))
            meta = {"profile": "polygon", "sketch_plane": plane,
                    "sketch_plane_offset": plane_offset if plane_offset is not None else 0,
                    "thickness": distance,
                    "extrusion_direction": direction,
                    "profile_points": points, "profile_ids": ids}
        else:
            raise ModelError("standalone Sketch supports Rectangle2D, Circle2D and Polygon2D")
        sketch.extend([_command("sketch.finish"),
            _command("solid.extrude", distance=command_value(distance),
                     direction=direction, body_name=name)])
        return sketch, meta

    if shape.kind == "tapered_box":
        # A straight front mask and a long, smoothly tapered rear housing.
        # The two section sketches are left in the native model history.
        original, start, inset = shape.data
        width, height, depth = original.data
        _require_positive(width, "taper width")
        _require_positive(height, "taper height")
        _require_positive(depth, "taper depth")
        if not 0 < pv(start) < pv(depth):
            raise ModelError("taper start lies outside the box")
        if not 0 < 2 * pv(inset) < min(pv(width), pv(height)):
            raise ModelError("taper inset is too large")

        x0, x1 = _half(width, True), _half(width)
        y0, y1 = _half(height, True), _half(height)

        def shifted(edge, inward):
            offset = command_value(inset)
            if isinstance(edge, str) or isinstance(offset, str):
                return f"({edge}) {'+' if inward else '-'} ({offset})"
            return edge + offset if inward else edge - offset

        front = f"{name} footprint"
        rear_start = f"{name} rear start"
        rear_end = f"{name} rear perimeter"

        def sketch_rectangle(sketch_name, offset, a, b):
            plane = dict(plane="XY", name=sketch_name)
            if offset is not None:
                plane["offset"] = command_value(offset)
            return [
                _command("sketch.create", **plane),
                _command("sketch.rectangle.two_point", p0=a, p1=b),
                _command("sketch.finish"),
            ]

        steps = sketch_rectangle(front, None, [x0, y0], [x1, y1])
        steps.append(_command(
            "solid.extrude", distance=command_value(start), body_name=name,
        ))
        steps.extend(sketch_rectangle(
            rear_start, start, [x0, y0], [x1, y1],
        ))
        steps.extend(sketch_rectangle(
            rear_end, depth,
            [shifted(x0, True), shifted(y0, True)],
            [shifted(x1, False), shifted(y1, False)],
        ))
        steps.append(_command(
            "solid.loft",
            sections=[{"sketch": rear_start}, {"sketch": rear_end}],
            operation="join", targets=[name],
        ))
        return steps, {
            "profile": "rectangle", "width": width, "depth": height,
            "thickness": depth,
            "origin": (-half(pv(width)), -half(pv(height)), 0),
        }

    raise ModelError(f"Expected a Box or explicit Sketch extrusion, got {shape.kind}")
