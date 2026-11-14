"""Ordered CAD features -> native SolidCraft commands.

Works on Box and explicit Sketch extrusions. Every feature is compiled
from its operation, not from a named example such as Plate.
"""
from math import isfinite
from fnmatch import fnmatchcase
from .core import (
    Shape,
    Edges,
    Faces,
    Depth,
    Anchor,
    Parameter,
    _DirectionSelector,
    _ProfileEdgeSelection,
    _dim_add,
    half,
    midpoint,
    pv,
    command_value,
)
from .history import History
from .compiler import ModelError, _command, _collect, _param_commands, _require_positive
from .placement import (
    _anchored_features, _base_rectangle, _combine, _shell_thickness,
)
from .sketches import compile_base


def _is_feature_tree(shape):
    if not isinstance(shape, Shape):
        return False
    if shape.kind in ("box", "placed_box", "tapered_box", "sketch_base_extrusion"):
        return True
    if shape.kind in ("fillet", "chamfer", "shell", "union", "difference", "material_assignment"):
        return _is_feature_tree(shape.data[0])
    return False


def _hole_commands(feature, position, name, refs=None):
    """Compile an explicitly positioned Hole to one or more native features."""
    if feature.kind != "hole":
        raise ModelError("native hole operation requires Hole")
    (
        diameter, depth, direction, countersink_d, countersink_angle,
        countersink_recess,
    ) = feature.data
    _require_positive(diameter, "hole diameter")

    point = tuple(position)
    concrete_point = [pv(v) for v in point]
    if not all(isfinite(v) for v in concrete_point):
        raise ModelError("hole position must be finite")

    direction_vector = (
        _vector(direction, "hole direction") if direction is not None else None
    )

    def simple_params(at, hole_diameter, hole_depth):
        params = dict(
            position=(
                [command_value(v) for v in at] if direction_vector is not None
                else [pv(v) for v in at]
            ),
            diameter=command_value(hole_diameter),
            targets=[name],
        )
        if hole_depth is not Depth.THROUGH_ALL:
            _require_positive(hole_depth, "hole depth")
            params["depth"] = command_value(hole_depth)
        if direction_vector is not None:
            params["direction"] = direction_vector
        if refs:
            params["references"] = refs
        return params

    if countersink_d is None:
        return [_command("solid.hole", **simple_params(point, diameter, depth))]

    _require_positive(countersink_d, "countersink diameter")
    if pv(countersink_d) <= pv(diameter):
        raise ModelError("countersink diameter must exceed hole diameter")
    angle = pv(countersink_angle)
    if not isfinite(angle) or angle <= 0 or angle >= 180:
        raise ModelError("countersink angle must be between 0 and 180 degrees")

    recess = pv(countersink_recess)
    if recess < 0:
        raise ModelError("countersink recess cannot be negative")

    commands = []
    entry = point
    remaining_depth = depth

    if recess:
        if direction_vector is None:
            raise ModelError(
                "a recessed countersink requires an explicit hole direction"
            )
        commands.append(_command(
            "solid.hole",
            **simple_params(point, countersink_d, countersink_recess),
        ))
        length = sum(v * v for v in direction_vector) ** 0.5
        unit = tuple(v / length for v in direction_vector)
        # A hole only moves along its axis.  Keep the other coordinates
        # unchanged instead of generating CAD expressions like
        # "(head_recess * 0)", which are misleading and unnecessary.
        entry = tuple(
            point[i] if abs(unit[i]) < 1e-12
            else _combine(point[i], countersink_recess * unit[i])
            for i in range(3)
        )
        if depth is not Depth.THROUGH_ALL:
            remaining_depth = _combine(depth, -countersink_recess)
            if pv(remaining_depth) <= 0:
                raise ModelError(
                    "hole depth must extend beyond the countersink recess"
                )

    params = simple_params(entry, diameter, remaining_depth)
    params.update(
        type="countersink",
        cs_diameter=command_value(countersink_d),
        cs_angle=command_value(countersink_angle),
    )
    # References describe the original entry face. They do not apply to the
    # recessed floor created by the first command.
    if recess:
        params.pop("references", None)
    commands.append(_command("solid.hole", **params))
    # Native SolidCraft 0.30.1 fails to Boolean-cut a +X countersink
    # if its counterbore has already been cut.  Both subtractive cuts
    # commute geometrically, so make the countersink first and its
    # shallow counterbore second.  Other orientations retain the
    # straightforward counterbore-then-countersink feature sequence.
    if (recess and direction_vector is not None
            and direction_vector[0] > 0
            and direction_vector[1] == 0
            and direction_vector[2] == 0):
        return [commands[-1], *commands[:-1]]
    return commands



def _resolve_profile_edges(base, selection):
    """Translate named XZ profile segments/vertices to native edge picks.

    The sketch may be extruded symmetric, positive or negative along Y and
    may itself sit on a shifted Y plane. Pick points are only used to select
    the native edge when the feature is authored; the resulting SolidCraft
    fillet/chamfer remains attached to that edge after parameter edits.
    """
    if not isinstance(selection, _ProfileEdgeSelection):
        return selection
    if (
        base.get("profile") != "polygon"
        or base.get("sketch_plane") != "XZ"
        or base.get("extrusion_direction") not in (
            "symmetric", "positive", "negative"
        )
    ):
        raise ModelError(
            "named profile edges require an XZ polygon extrusion"
        )
    points = base["profile_points"]
    names = base["profile_ids"]
    if names is None:
        raise ModelError("Polygon2D must define ids= or named points to select profile edges")
    for pattern in selection.patterns:
        if not any(fnmatchcase(label, pattern) for label in names):
            raise ModelError(f"no polygon segment or vertex matches {pattern!r}")

    matches = [
        i for i, label in enumerate(names)
        if any(fnmatchcase(label, pattern) for pattern in selection.patterns)
    ]
    plane_y = pv(base.get("sketch_plane_offset", 0))
    thickness = pv(base["thickness"])
    direction = base["extrusion_direction"]
    if direction == "symmetric":
        start_y = plane_y - half(thickness)
        end_y = plane_y + half(thickness)
    elif direction == "positive":
        start_y = plane_y
        end_y = plane_y + thickness
    else:
        start_y = plane_y
        end_y = plane_y - thickness

    if selection.kind == "vertices":
        sweep_mid_y = midpoint(start_y, end_y)
        return [
            (pv(points[i][0]), sweep_mid_y, -pv(points[i][1]))
            for i in matches
        ]
    if selection.kind != "segments":
        raise ModelError(f"unsupported profile edge selection: {selection.kind}")

    picks = []
    for y in (start_y, end_y):
        for i in matches:
            a, b = points[i], points[(i + 1) % len(points)]
            picks.append((
                midpoint(pv(a[0]), pv(b[0])),
                y,
                -midpoint(pv(a[1]), pv(b[1])),
            ))
    return picks


def _resolve_direction_edges(base, selection):
    """Resolve BOSL2-style direction pairs to stable edge pick points."""
    if isinstance(selection, _DirectionSelector):
        selectors = (selection,)
    elif (
        isinstance(selection, (tuple, list))
        and selection
        and all(isinstance(item, _DirectionSelector) for item in selection)
    ):
        selectors = tuple(selection)
    else:
        return selection

    if base.get("profile") != "rectangle":
        raise ModelError("direction edge selectors require a rectangular solid")

    origin = base["origin"]
    dimensions = (
        base["width"],
        base["depth"],
        base["thickness"],
    )

    picks = []
    for selector in selectors:
        if sum(component != 0 for component in selector.vector) != 2:
            raise ModelError(
                "an edge selector must combine exactly two cardinal directions"
            )
        point = []
        for minimum, dimension, side in zip(
            origin,
            dimensions,
            selector.vector,
        ):
            if side < 0:
                point.append(minimum)
            elif side > 0:
                point.append(_dim_add(minimum, dimension))
            else:
                point.append(_dim_add(minimum, half(dimension)))
        picks.append(tuple(point))
    return picks


def _fillet_command(base, radius, edges, name):
    r = _require_positive(radius, "fillet radius")
    if edges is Edges.VERTICAL:
        if base["profile"] != "rectangle":
            raise ModelError("vertical-edge selection requires a rectangular base")
        w, d, h = (pv(base[k]) for k in ("width", "depth", "thickness"))
        if r * 2 >= min(w, d):
            raise ModelError("fillet radius exceeds rectangular base dimensions")
        x, y, z = (pv(v) for v in base["origin"])
        if z != 0:
            raise ModelError("vertical fillet of shifted base not supported")
        picks = [[x + dx, y + dy, half(h)]
                 for dx, dy in ((0, 0), (w, 0), (w, d), (0, d))]
        return _command(
            "solid.fillet",
            edges=picks,
            radius=command_value(radius),
            body=name,
        )
    picks = [[pv(v) for v in point] for point in edges]
    if not all(isfinite(v) for point in picks for v in point):
        raise ModelError("fillet edge selection must be finite")
    return _command("solid.fillet", edges=picks, radius=command_value(radius), body=name)


def _chamfer_command(distance, edges, name):
    _require_positive(distance, "chamfer distance")
    picks = [[pv(v) for v in point] for point in edges]
    if not all(isfinite(v) for point in picks for v in point):
        raise ModelError("chamfer edge selection must be finite")
    return _command(
        "solid.chamfer",
        edges=picks,
        distance=command_value(distance),
        body=name,
    )


def _face_point(base, face):
    """Return a stable authoring pick on a named face of a rectangular base."""
    if base.get("profile") != "rectangle":
        raise ModelError("named Faces currently require a rectangular base")
    x, y, z = (pv(v) for v in base["origin"])
    width = pv(base["width"])
    depth = pv(base["depth"])
    height = pv(base["thickness"])
    points = {
        Faces.TOP: [x + half(width), y + half(depth), z + height],
        Faces.BOTTOM: [x + half(width), y + half(depth), z],
        Faces.LEFT: [x, y + half(depth), z + half(height)],
        Faces.RIGHT: [x + width, y + half(depth), z + half(height)],
        Faces.FRONT: [x + half(width), y, z + half(height)],
        Faces.BACK: [x + half(width), y + depth, z + half(height)],
    }
    return points[face]


def _shell_command(base, thickness, faces, name):
    _require_positive(thickness, "shell thickness")
    return _command(
        "solid.shell",
        faces=[_face_point(base, face) for face in faces],
        thickness=command_value(thickness),
        body=name,
    )


def _vector(values, label):
    concrete = [pv(v) for v in values]
    if len(concrete) != 3 or not all(isfinite(v) for v in concrete):
        raise ModelError(f"{label} must be a finite 3D direction")
    if concrete == [0, 0, 0]:
        raise ModelError(f"{label} cannot be the zero vector")
    return concrete


def _plastic_feature_command(feature, position, name):
    """Compile one native SolidCraft plastic feature at an explicit face pick."""
    point = [pv(v) for v in position]
    if not all(isfinite(v) for v in point):
        raise ModelError("plastic feature position must be finite")

    if feature.kind == "lip":
        width, height = feature.data
        _require_positive(width, "lip width")
        _require_positive(height, "lip height")
        return _command(
            "plastic.lip",
            face=point,
            width=command_value(width),
            height=command_value(height),
            body=name,
        )

    if feature.kind == "snap_fit":
        length, thickness, width, catch_depth, catch_length, hook, direction = feature.data
        for value, label in (
            (length, "snap-fit length"),
            (thickness, "snap-fit thickness"),
            (width, "snap-fit width"),
            (catch_depth, "snap-fit catch depth"),
            (catch_length, "snap-fit catch length"),
        ):
            _require_positive(value, label)
        params = dict(
            position=point,
            hook=_vector(hook, "snap-fit hook"),
            length=command_value(length),
            thickness=command_value(thickness),
            width=command_value(width),
            catch_depth=command_value(catch_depth),
            catch_length=command_value(catch_length),
            body=name,
        )
        if direction is not None:
            params["direction"] = _vector(direction, "snap-fit direction")
        return _command("plastic.snap_fit", **params)

    if feature.kind == "boss":
        diameter, height, hole_diameter, direction = feature.data
        _require_positive(diameter, "boss diameter")
        _require_positive(height, "boss height")
        params = dict(
            position=point,
            diameter=command_value(diameter),
            height=command_value(height),
            body=name,
        )
        if hole_diameter is not None:
            _require_positive(hole_diameter, "boss hole diameter")
            params["hole_diameter"] = command_value(hole_diameter)
        if direction is not None:
            params["direction"] = _vector(direction, "boss direction")
        return _command("plastic.boss", **params)

    if feature.kind == "rest":
        width, height, length, along, direction = feature.data
        _require_positive(width, "rest width")
        _require_positive(height, "rest height")
        params = dict(
            position=point,
            width=command_value(width),
            height=command_value(height),
            body=name,
        )
        if length is not None:
            _require_positive(length, "rest length")
            params["length"] = command_value(length)
        if along is not None:
            params["along"] = _vector(along, "rest along")
        if direction is not None:
            params["direction"] = _vector(direction, "rest direction")
        return _command("plastic.rest", **params)

    raise ModelError(f"unsupported plastic feature {feature.kind}")


def _attached_hole_commands(child, target, parent_anchor, resolved, name):
    """Compile Hole intent as one editable sketch plus one cut feature."""
    feature = child.data[0] if child.kind == "linear_pattern" else child
    if feature.kind != "hole":
        raise ModelError("expected Hole feature")
    if parent_anchor is not Anchor.TOP:
        raise ModelError("Hole.attach() currently starts drilling from Anchor.TOP")

    (
        diameter, depth, hole_direction, countersink_d, countersink_angle,
        countersink_recess,
    ) = feature.data
    _require_positive(diameter, "hole diameter")
    if (hole_direction is not None or countersink_d is not None
            or pv(countersink_recess) != 0):
        raise ModelError(
            "directional or countersunk Hole currently requires explicit .at() placement"
        )
    (_, _), (_, _, origin_z), thickness = _base_rectangle(target)
    base_top = thickness if pv(origin_z) == 0 else _combine(origin_z, thickness)
    entry_z = base_top
    on_base_top = True

    # If the current body ends in a centered Cylinder attached to its top,
    # the next Hole starts on that boss top. Keep the symbolic height so the
    # generated Bore sketch remains parametrically tied to the base thickness.
    if target.kind == "union":
        previous, attached = target.data
        if attached.kind == "anchored":
            boss, boss_parent, boss_parent_anchor, boss_child_anchor, boss_offset = attached.data
            if (boss.kind == "cylinder" and boss_parent == previous
                    and boss_parent_anchor is Anchor.TOP
                    and boss_child_anchor is Anchor.BOTTOM
                    and all(pv(v) == 0 for v in boss_offset)):
                boss_height, _, boss_axis = boss.data
                if boss_axis != "Z":
                    raise ModelError("attached boss Cylinder must use Axis.Z")
                entry_z = (base_top + boss_height
                           if isinstance(boss_height, (int, float))
                           else _combine(base_top, boss_height))
                on_base_top = False

    if depth is Depth.THROUGH_ALL:
        if on_base_top:
            # Preserve the editable Sample Plate convention: XY/base-plane
            # sketch and positive cut through the plate thickness.
            sketch_z = origin_z
            distance = thickness
            direction = "positive"
        else:
            # A bore starting on a joined boss is sketched at its entry face
            # and cuts back through the complete current height.
            sketch_z = entry_z
            distance = (entry_z if pv(origin_z) == 0
                        else _combine(entry_z, -pv(origin_z)))
            direction = "negative"
    else:
        _require_positive(depth, "hole depth")
        sketch_z = entry_z
        distance = depth
        direction = "negative"

    label = "Holes" if child.kind == "linear_pattern" else (
        "Bore" if not on_base_top else "Hole")
    plane = {"plane": "XY", "name": label}
    if pv(sketch_z):
        plane["offset"] = command_value(sketch_z)

    operations = [_command("sketch.create", **plane)]
    for primitive, position, _refs in resolved:
        hole_diameter = primitive.data[0]
        operations.append(_command(
            "sketch.circle.center",
            center=position[:2],
            diameter=command_value(hole_diameter),
        ))
    operations.extend([
        _command("sketch.finish"),
        _command("solid.extrude",
                 distance=command_value(distance),
                 direction=direction,
                 operation="cut",
                 targets=[name],
                 name=label),
    ])
    return operations


def _sketch_boss_commands(feature, position, name, *, feature_name=None):
    """Experimental sketch-based lowering for a semantic Boss object."""
    diameter, height, hole_diameter, direction = feature.data
    _require_positive(diameter, "boss diameter")
    _require_positive(height, "boss height")
    if direction is not None and [pv(v) for v in direction] != [0, 0, 1]:
        raise ModelError("sketch-based Boss prototype currently supports +Z only")

    x, y, z = position
    label = feature_name or "Boss"
    plane = dict(plane="XY", name=label)
    if pv(z):
        plane["offset"] = command_value(z)

    commands = [
        _command("sketch.create", **plane),
        _command(
            "sketch.circle.center",
            center=[command_value(x), command_value(y)],
            diameter=command_value(diameter),
        ),
        _command("sketch.finish"),
        _command(
            "solid.extrude",
            distance=command_value(height),
            direction="positive",
            operation="join",
            targets=[name],
            name=label,
        ),
    ]

    if hole_diameter is not None:
        _require_positive(hole_diameter, "boss hole diameter")
        top = _combine(z, height)
        hole_label = f"{label} hole"
        hole_plane = dict(plane="XY", name=hole_label)
        if pv(top):
            hole_plane["offset"] = command_value(top)
        commands.extend([
            _command("sketch.create", **hole_plane),
            _command(
                "sketch.circle.center",
                center=[command_value(x), command_value(y)],
                diameter=command_value(hole_diameter),
            ),
            _command("sketch.finish"),
            _command(
                "solid.extrude",
                distance=command_value(height),
                direction="negative",
                operation="cut",
                targets=[name],
                name=hole_label,
            ),
        ])
    return commands


def _attached_commands(shape, original, feature, name, *, feature_name=None):
    child, target, parent_anchor, child_anchor, offset = feature.data
    if target != original:
        raise ModelError("attached feature must target the body being modified")
    try:
        resolved = _anchored_features(feature)
    except (ValueError, TypeError) as exc:
        raise ModelError(str(exc)) from exc

    attached_primitive = child.data[0] if child.kind == "linear_pattern" else child
    if attached_primitive.kind == "hole":
        return _attached_hole_commands(
            child, target, parent_anchor, resolved, name)
    if attached_primitive.kind in ("lip", "snap_fit", "boss", "rest"):
        if shape.kind != "union":
            raise ModelError("plastic features are added with +")
        if (
            attached_primitive.kind == "boss"
            and attached_primitive.history is History.SKETCH
        ):
            operations = []
            for primitive, position, _refs in resolved:
                operations.extend(
                    _sketch_boss_commands(
                        primitive,
                        position,
                        name,
                        feature_name=feature_name,
                    )
                )
            return operations
        return [
            _plastic_feature_command(primitive, position, name)
            for primitive, position, _refs in resolved
        ]

    operations = []
    for primitive, position, refs in resolved:
        height, diameter, axis = primitive.data
        _require_positive(height, "cylinder height")
        _require_positive(diameter, "cylinder diameter")
        if axis != "Z":
            raise ModelError("attached Cylinder must use Axis.Z")
        params = dict(
            height=command_value(height),
            diameter=command_value(diameter),
            base=position,
            axis=axis,
            operation="join" if shape.kind == "union" else "cut",
            targets=[name],
        )
        if refs:
            params["references"] = refs
        if feature_name is not None:
            params["name"] = feature_name
        operations.append(_command("solid.cylinder", **params))
    return operations


def _explicit_sketch_commands(shape, original, feature, name):
    """Compile an explicitly authored named sketch and its extrusion."""
    sketch_name, target, parent_anchor, plane_info, profiles, distance, direction = feature.data
    plane_name, sketch_origin = plane_info
    if target != original:
        raise ModelError("explicit Sketch must target the body being modified")
    if shape.kind not in ("union", "difference"):
        raise ModelError("explicit Sketch extrusion must be added or subtracted")

    (width, depth), (x, y, z), thickness = _base_rectangle(target)
    if thickness is None:
        raise ModelError("explicit Sketch requires a rectangular solid")

    if plane_name is not None:
        if sketch_origin is not None:
            orientation = {
                "XY": ([1, 0, 0], [0, 1, 0]),
                "XZ": ([1, 0, 0], [0, 0, 1]),
                "YZ": ([0, 1, 0], [0, 0, 1]),
            }
            x_dir, y_dir = orientation[plane_name]
            plane = dict(
                plane={"origin": [pv(v) for v in sketch_origin],
                       "x_dir": x_dir, "y_dir": y_dir},
                name=sketch_name,
            )
        else:
            plane = dict(plane=plane_name, name=sketch_name)
        relative_origin = (0, 0)
    else:
        if parent_anchor is Anchor.TOP:
            plane_z = _combine(z, thickness)
        elif parent_anchor is Anchor.BOTTOM:
            plane_z = z
        elif parent_anchor is Anchor.INNER_BOTTOM:
            wall = _shell_thickness(target)
            if wall is None:
                raise ModelError("Anchor.INNER_BOTTOM requires a shelled body")
            plane_z = _combine(z, wall)
        elif parent_anchor is Anchor.CENTER:
            plane_z = _combine(z, half(thickness))
        else:
            raise ModelError("unsupported explicit Sketch anchor")

        plane = dict(plane="XY", name=sketch_name)
        if pv(plane_z):
            plane["offset"] = command_value(plane_z)
        relative_origin = (_combine(x, half(width)), _combine(y, half(depth)))

    commands = [_command("sketch.create", **plane)]

    for profile, offset in profiles:
        ox = _combine(relative_origin[0], offset[0])
        oy = _combine(relative_origin[1], offset[1])

        if profile.kind == "circle":
            diameter = profile.data[0]
            _require_positive(diameter, "sketch circle diameter")
            commands.append(
                _command(
                    "sketch.circle.center",
                    center=[command_value(ox), command_value(oy)],
                    diameter=command_value(diameter),
                )
            )
            continue

        if profile.kind in ("rectangle", "rounded_rectangle"):
            rectangle_width, rectangle_height = profile.data[:2]
            _require_positive(rectangle_width, "sketch rectangle width")
            _require_positive(rectangle_height, "sketch rectangle height")
            params = dict(
                p0=[command_value(ox), command_value(oy)],
                p1=[
                    command_value(_combine(ox, rectangle_width)),
                    command_value(_combine(oy, rectangle_height)),
                ],
            )
            if profile.kind == "rounded_rectangle":
                radius = profile.data[2]
                _require_positive(radius, "sketch rounded rectangle radius")
                if pv(radius) * 2 >= min(
                        pv(rectangle_width), pv(rectangle_height)):
                    raise ModelError("rounded rectangle radius exceeds half the shorter side")
                params["radius"] = command_value(radius)
                command = "sketch.rectangle.rounded"
            else:
                command = "sketch.rectangle.two_point"
            commands.append(_command(command, **params))
            continue

        if profile.kind == "text":
            text, height, font = profile.data
            _require_positive(height, "sketch text height")
            commands.append(_command(
                "sketch.text", text=text,
                at=[command_value(ox), command_value(oy)],
                height=command_value(height), font=font,
            ))
            continue
        raise ModelError("explicit Sketch supports Circle2D, Rectangle2D, RoundedRectangle2D or Text2D")

    commands.append(_command("sketch.finish"))

    extrude = dict(
        operation="join" if shape.kind == "union" else "cut",
        targets=[name],
        name=sketch_name,
    )
    if distance is Depth.THROUGH_ALL:
        if shape.kind != "difference":
            raise ModelError("Depth.THROUGH_ALL is only supported for Sketch cuts")
        extrude["through_all"] = True
    else:
        extrude["distance"] = command_value(distance)
        extrude["direction"] = direction

    commands.append(_command("solid.extrude", **extrude))
    return commands


def _to_commands(shape, name):
    if shape.kind in ("box", "placed_box", "tapered_box", "sketch_base_extrusion"):
        return compile_base(shape, name)
    if shape.kind == "material_assignment":
        base_shape, material, density, color = shape.data
        steps, base = _to_commands(base_shape, name)
        creation = dict(name=material, density_g_cm3=density)
        if color is not None:
            creation["color"] = color
        return steps + [
            _command("material.create", **creation),
            _command("material.assign", bodies=[name], material=material),
        ], base
    if shape.kind == "shell":
        original, thickness, faces = shape.data
        steps, base = _to_commands(original, name)
        return steps + [_shell_command(base, thickness, faces, name)], base
    if shape.kind == "fillet":
        original, radius, edges = shape.data
        steps, base = _to_commands(original, name)
        resolved = _resolve_profile_edges(base, edges)
        resolved = _resolve_direction_edges(base, resolved)
        return steps + [_fillet_command(base, radius, resolved, name)], base
    if shape.kind == "chamfer":
        original, distance, edges = shape.data
        steps, base = _to_commands(original, name)
        return steps + [_chamfer_command(distance, _resolve_profile_edges(base, edges), name)], base
    if shape.kind in ("union", "difference"):
        original, added = shape.data
        steps, base = _to_commands(original, name)
        feature_name = None
        if added.kind == "labeled":
            added, feature_name = added.data
        if added.kind == "anchored":
            return steps + _attached_commands(
                shape, original, added, name, feature_name=feature_name), base
        if added.kind == "explicit_sketch_extrusion":
            return steps + _explicit_sketch_commands(
                shape, original, added, name
            ), base
        if added.kind == "placed3d" and added.data[0].kind in (
                "lip", "snap_fit", "boss", "rest"):
            if shape.kind != "union":
                raise ModelError("plastic features are added with +")
            feature, x, y, z = added.data
            return steps + [
                _plastic_feature_command(feature, (x, y, z), name)
            ], base
        if added.kind == "placed3d" and added.data[0].kind == "hole":
            hole, x, y, z = added.data
            return steps + _hole_commands(hole, (x, y, z), name), base
        if added.kind == "hole":
            raise ModelError("Hole must be positioned with .attach() or .at()")
        if added.kind in ("lip", "snap_fit", "boss", "rest"):
            raise ModelError(
                f"{added.kind} must be positioned with .attach() or .at()"
            )
        if added.kind in ("cylinder", "placed3d"):
            if added.kind == "placed3d":
                primitive, x, y, z = added.data
            else:
                primitive, x, y, z = added, 0, 0, 0
            if primitive.kind != "cylinder":
                raise ModelError("boolean primitive requires Cylinder")
            height, diameter, axis = primitive.data
            _require_positive(height, "cylinder height")
            _require_positive(diameter, "cylinder diameter")
            return steps + [
                _command("solid.cylinder",
                         height=command_value(height),
                         diameter=command_value(diameter),
                         base=[command_value(x), command_value(y), command_value(z)],
                         axis=axis, operation="join" if shape.kind == "union" else "cut",
                         targets=[name]),
            ], base
        raise ModelError(f"unsupported CAD feature {added.kind}")
    raise ModelError(f"unsupported CAD solid {shape.kind}")


def compile_features(shape, name):
    """Compile native commands with deterministic, source-oriented parameters."""
    steps, _ = _to_commands(shape, name)
    # On an extruded polygon the sweep distance is the first independent
    # dimension of the feature. Keep it before coordinates of its profile.
    # XY rectangular footprints instead list their plan dimensions first.
    root = shape
    while root.kind in ("fillet", "chamfer", "shell", "union", "difference", "material_assignment"):
        root = root.data[0]
    if root.kind == "sketch_base_extrusion":
        profiles = root.data[4]
        profile = profiles[0][0] if len(profiles) == 1 else None
        if profile is not None and profile.kind == "polygon":
            parameters = _collect((root.data[5], shape))
        else:
            parameters = _collect(shape)
    else:
        parameters = _collect(shape)
    return _param_commands(parameters) + steps
