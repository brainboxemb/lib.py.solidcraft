"""Internal reusable-model and assembly nodes.

User scripts keep ordinary class names such as Block() and Enclosure().
These nodes are the compiler-facing representation; users do not need to
construct Component or Occurrence objects explicitly.
"""
from dataclasses import dataclass, replace
from math import isfinite

from .core import (
    Anchor,
    AnchorFrame,
    AnchorTopology,
    Axis,
    Shape,
    _DirectionSelector,
    _dim_add,
    _selector_anchor,
    half,
    midpoint,
    parameters_in,
    pv,
)


@dataclass(frozen=True)
class ModelDefinition:
    """One reusable user-model definition before SolidCraft lowering."""

    class_name: str
    parameters: tuple[tuple[str, float], ...]
    shape: Shape
    fixed_inputs: tuple[tuple[str, float], ...] = ()
    external_parameters: tuple[tuple[str, float], ...] = ()
    input_bindings: tuple[tuple[str, str], ...] = ()
    anchors: tuple[tuple[str, AnchorFrame | AnchorTopology], ...] = ()

    @property
    def key(self):
        return (
            self.class_name,
            self.parameters,
            self.fixed_inputs,
            self.input_bindings,
            self.anchors,
        )


@dataclass(frozen=True)
class Attachment:
    """Associative face-to-face relationship between two model occurrences."""

    target: "ModelInstance"
    parent: Anchor | str | AnchorFrame | AnchorTopology | None
    child: Anchor | str | AnchorFrame | AnchorTopology | None
    offset: tuple[object, object]
    gap: object = 0
    angle: float | None = None
    as_built: bool = False


def _custom_anchor(instance, name):
    try:
        return dict(instance.definition.anchors)[name]
    except KeyError as exc:
        raise ValueError(
            f"{instance.definition.class_name} has no component anchor {name!r}"
        ) from exc


def _resolve_anchor_reference(instance, value):
    """Resolve a standard, composed, named, or direct attachment frame."""
    if isinstance(value, _DirectionSelector):
        return _selector_anchor(value)
    if isinstance(value, (Anchor, AnchorFrame, AnchorTopology)):
        return value
    if isinstance(value, str):
        try:
            return Anchor(value)
        except ValueError:
            _custom_anchor(instance, value)
            return value
    raise ValueError(
        "component attach requires a cardinal selector, Anchor, AnchorFrame, "
        "AnchorTopology or anchor name"
    )


def _anchor_local_point(instance, anchor):
    if isinstance(anchor, Anchor):
        return _anchor_point(instance, anchor)
    if isinstance(anchor, AnchorFrame):
        return anchor.origin
    if isinstance(anchor, AnchorTopology):
        return anchor.corner if anchor.corner is not None else anchor.edge
    custom = _custom_anchor(instance, anchor)
    if isinstance(custom, AnchorFrame):
        return custom.origin
    return custom.corner if custom.corner is not None else custom.edge


def _unwrap_rectangular_shape(shape):
    """Follow modifiers that retain the base component's nominal bounds."""
    while shape.kind in (
        "material_assignment",
        "fillet",
        "chamfer",
        "shell",
        "union",
        "difference",
    ):
        shape = shape.data[0]
    return shape


def _xz_polygon_rectangle_bounds(shape):
    """Bounds for one rectangular XZ polygon extrusion.

    Polygon2D stores XZ sketch-local coordinates as (x, -z). The explicit
    Sketch may shift its XZ plane along world Y through Sketch(offset=...).
    This helper validates the four corners instead of treating an arbitrary
    polygon bbox as a rectangular attachment target.
    """
    shape = _unwrap_rectangular_shape(shape)
    if shape.kind != "sketch_base_extrusion":
        raise ValueError("not an XZ Sketch extrusion")

    _, plane, origin, plane_offset, profiles, distance, direction = shape.data
    if plane != "XZ" or origin is not None:
        raise ValueError("not a supported XZ Sketch extrusion")
    if len(profiles) != 1:
        raise ValueError("XZ attachment rectangle requires one profile")

    profile, profile_offset = profiles[0]
    if profile.kind != "polygon" or profile.data[1] != "XZ":
        raise ValueError("not an XZ polygon")
    if any(pv(value) != 0 for value in profile_offset):
        raise ValueError("XZ attachment polygon must use the Sketch origin")
    plane_y = 0.0 if plane_offset is None else pv(plane_offset)

    points = profile.data[0]
    if len(points) != 4:
        raise ValueError("XZ attachment rectangle requires four vertices")
    world_points = [(pv(u), -pv(v)) for u, v in points]
    xs = [point[0] for point in world_points]
    zs = [point[1] for point in world_points]
    xmin, xmax = min(xs), max(xs)
    zmin, zmax = min(zs), max(zs)
    if xmin == xmax or zmin == zmax:
        raise ValueError("degenerate XZ attachment rectangle")
    expected = {
        (xmin, zmin), (xmin, zmax), (xmax, zmin), (xmax, zmax)
    }
    if set(world_points) != expected:
        raise ValueError("XZ polygon is not an axis-aligned rectangle")

    depth = pv(distance)
    if depth <= 0:
        raise ValueError("attachment extrusion distance must be positive")
    if direction == "positive":
        ymin, ymax = plane_y, plane_y + depth
    elif direction == "negative":
        ymin, ymax = plane_y - depth, plane_y
    elif direction == "symmetric":
        ymin, ymax = plane_y - half(depth), plane_y + half(depth)
    else:
        raise ValueError("unsupported extrusion direction")

    return ((xmin, xmax), (ymin, ymax), (zmin, zmax))


def _rectangular_bounds(instance):
    """Return local axis-aligned bounds for a supported rectangular component."""
    from .placement import _base_rectangle

    shape = _unwrap_rectangular_shape(instance.definition.shape)
    try:
        (width, depth), (x, y, z), height = _base_rectangle(shape)
    except ValueError:
        try:
            return _xz_polygon_rectangle_bounds(shape)
        except ValueError as exc:
            raise ValueError(
                "component attach requires a supported rectangular model"
            ) from exc

    width, depth, height = map(pv, (width, depth, height))
    x, y, z = map(pv, (x, y, z))
    return (
        (x, x + width),
        (y, y + depth),
        (z, z + height),
    )


_CORNER_ANCHORS = {
    Anchor.FRONT_TOP_LEFT,
    Anchor.FRONT_TOP_RIGHT,
    Anchor.FRONT_BOTTOM_LEFT,
    Anchor.FRONT_BOTTOM_RIGHT,
    Anchor.BACK_TOP_LEFT,
    Anchor.BACK_TOP_RIGHT,
    Anchor.BACK_BOTTOM_LEFT,
    Anchor.BACK_BOTTOM_RIGHT,
}


def _anchor_point(instance, anchor):
    """Local point represented by one reusable-component anchor."""
    bounds = _rectangular_bounds(instance)
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds
    xmid = midpoint(xmin, xmax)
    ymid = midpoint(ymin, ymax)
    zmid = midpoint(zmin, zmax)
    points = {
        Anchor.CENTER: (xmid, ymid, zmid),
        Anchor.LEFT: (xmin, ymid, zmid),
        Anchor.RIGHT: (xmax, ymid, zmid),
        Anchor.FRONT: (xmid, ymin, zmid),
        Anchor.BACK: (xmid, ymax, zmid),
        Anchor.BOTTOM: (xmid, ymid, zmin),
        Anchor.TOP: (xmid, ymid, zmax),
        Anchor.FRONT_TOP_LEFT: (xmin, ymin, zmax),
        Anchor.FRONT_TOP_RIGHT: (xmax, ymin, zmax),
        Anchor.FRONT_BOTTOM_LEFT: (xmin, ymin, zmin),
        Anchor.FRONT_BOTTOM_RIGHT: (xmax, ymin, zmin),
        Anchor.BACK_TOP_LEFT: (xmin, ymax, zmax),
        Anchor.BACK_TOP_RIGHT: (xmax, ymax, zmax),
        Anchor.BACK_BOTTOM_LEFT: (xmin, ymax, zmin),
        Anchor.BACK_BOTTOM_RIGHT: (xmax, ymax, zmin),
    }
    if anchor not in points:
        raise ValueError(f"{anchor} is not a supported assembly anchor")
    return points[anchor]


def _corner_origin_points(instance, anchor):
    """Return edge, face and corner picks for a native SolidCraft corner origin.

    The chosen edge is the vertical left/right edge of the front/back face.
    Its topology stays the same when height changes; SolidCraft stores that
    edge, the face and the second corner edge by name, so the origin follows
    saved-design dimension changes symmetrically on both sides.
    """
    if anchor not in _CORNER_ANCHORS:
        raise ValueError("corner origin requires a corner Anchor")
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = _rectangular_bounds(instance)
    xmid = midpoint(xmin, xmax)
    zmid = midpoint(zmin, zmax)

    front = anchor.value.startswith("front_")
    left = anchor.value.endswith("_left")
    top = "_top_" in anchor.value
    y = ymin if front else ymax
    x = xmin if left else xmax
    z = zmax if top else zmin
    edge = (x, y, zmid)
    on = (xmid, y, zmid)
    corner = (x, y, z)
    return edge, on, corner


def _corner_native_x(anchor):
    """Native SolidCraft clocking axis for one standard corner anchor."""
    mapping = {
        Anchor.FRONT_TOP_LEFT: (0.0, 0.0, -1.0),
        Anchor.FRONT_TOP_RIGHT: (-1.0, 0.0, 0.0),
        Anchor.FRONT_BOTTOM_RIGHT: (0.0, 0.0, 1.0),
        Anchor.FRONT_BOTTOM_LEFT: (1.0, 0.0, 0.0),
        Anchor.BACK_TOP_LEFT: (1.0, 0.0, 0.0),
        Anchor.BACK_TOP_RIGHT: (0.0, 0.0, -1.0),
        Anchor.BACK_BOTTOM_RIGHT: (-1.0, 0.0, 0.0),
        Anchor.BACK_BOTTOM_LEFT: (0.0, 0.0, 1.0),
    }
    try:
        return mapping[anchor]
    except KeyError as exc:
        raise ValueError("corner clocking requires a corner Anchor") from exc


def _corner_normal(anchor):
    """Outward normal of the front/back face owning a corner anchor."""
    if anchor not in _CORNER_ANCHORS:
        raise ValueError("corner normal requires a corner Anchor")
    return (
        (0.0, -1.0, 0.0)
        if anchor.value.startswith("front_")
        else (0.0, 1.0, 0.0)
    )


def _anchor_origin(instance, anchor, occurrence):
    """Native SolidCraft joint-origin spec for one component anchor."""
    if instance.rotation is not None and anchor in _CORNER_ANCHORS:
        raise ValueError(
            "corner anchors on explicitly rotated occurrences are not supported yet"
        )

    def world(point):
        return [
            point[i] + instance.translation[i]
            for i in range(3)
        ]

    if anchor in _CORNER_ANCHORS:
        edge, on, corner = _corner_origin_points(instance, anchor)
        return {
            "occurrence": occurrence,
            "edge": world(edge),
            "on": world(on),
            "corner": world(corner),
        }
    return {
        "occurrence": occurrence,
        "face": world(_anchor_point(instance, anchor)),
    }


def _face_offset(anchor, offset):
    """Map a two-value face offset into XYZ."""
    u, v = offset
    if anchor in (Anchor.LEFT, Anchor.RIGHT):
        return (0.0, u, v)
    if anchor in (Anchor.FRONT, Anchor.BACK):
        return (u, 0.0, v)
    if anchor in (Anchor.TOP, Anchor.BOTTOM):
        return (u, v, 0.0)
    if anchor is Anchor.CENTER:
        return (u, v, 0.0)
    if anchor in _CORNER_ANCHORS and u == 0 and v == 0:
        return (0.0, 0.0, 0.0)
    raise ValueError("unsupported assembly anchor")


@dataclass(frozen=True)
class ModelInstance:
    """One placed occurrence of a reusable model definition."""

    definition: ModelDefinition
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    attachment: Attachment | None = None
    rotation: tuple[tuple[float, float, float], float] | None = None
    group_name: str | None = None
    name: str | None = None
    flattened_parameters: tuple[str, ...] = ()

    def group(self, name):
        """Keep this occurrence in a named native subassembly component."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("group name must be non-empty text")
        if self.group_name is not None and self.group_name != name:
            raise ValueError("an occurrence cannot belong to multiple groups")
        return replace(self, group_name=name)

    def copy(self):
        """Another unnamed occurrence of the same reusable component."""
        return replace(self, attachment=None, name=None)

    def move(self, x=0, y=0, z=0):
        """Translate this occurrence without changing shared component geometry.

        Keep Parameter/Expression values symbolic so parameter-driven
        placement stays associative instead of being flattened to the current
        Python value. The compiler lowers that intent to the native placement
        mechanism supported by the targeted SolidCraft version.
        """
        values = (x, y, z)
        concrete = tuple(pv(value) for value in values)
        if not all(isfinite(value) for value in concrete):
            raise ValueError("model move() requires finite coordinates")
        current = self.translation
        return replace(
            self,
            translation=tuple(
                _dim_add(current[i], values[i])
                for i in range(3)
            ),
            attachment=None,
        )

    def rotate(self, axis=(0, 0, 1), degrees=None):
        """Set this occurrence's absolute local-axis orientation in degrees.

        Named axis tokens allow concise calls such as rotate(X, 180) and
        rotate(Y, 90). The explicit tuple form remains supported:
        rotate(axis=(0, 1, 0), degrees=90).

        Rotates only the placement of the shared component definition.
        The pivot is the component's local origin; translation is preserved.
        One axis-angle orientation is supported, not chained Euler rotations.
        """
        if degrees is None:
            raise ValueError("model rotate() requires an angle in degrees")
        if isinstance(axis, Axis):
            axis = axis.value
        if isinstance(axis, str):
            named_axes = {
                "X": (1, 0, 0),
                "Y": (0, 1, 0),
                "Z": (0, 0, 1),
            }
            try:
                axis = named_axes[axis]
            except KeyError as exc:
                raise ValueError("model rotate() named axis must be X, Y or Z") from exc
        if (not isinstance(axis, (tuple, list)) or len(axis) != 3):
            raise ValueError("model rotate() axis must be X, Y, Z or an XYZ triple")
        symbolic = tuple(
            parameter.name
            for parameter in parameters_in(*axis, degrees)
        )
        flattened = tuple(dict.fromkeys(
            (*self.flattened_parameters, *symbolic)
        ))
        try:
            values = tuple(float(pv(value)) for value in axis)
            angle = float(pv(degrees))
        except (TypeError, ValueError) as exc:
            raise ValueError("model rotate() requires numeric axis and degrees") from exc
        if not all(isfinite(v) for v in (*values, angle)):
            raise ValueError("model rotate() requires finite coordinates and angle")
        if sum(v * v for v in values) <= 0:
            raise ValueError("model rotate() axis must be non-zero")
        return replace(
            self,
            rotation=(values, angle),
            attachment=None,
            flattened_parameters=flattened,
        )

    def attach(self, target, *, parent=Anchor.RIGHT, child=Anchor.LEFT,
               offset=(0, 0), gap=0, angle=None, as_built=False):
        """Attach this component rigidly to another component.

        ``gap`` is the normal distance between the references.
        ``angle`` is their relative turn in degrees around the attachment
        normal. Both stay native SolidCraft joint values.

        ``as_built=True`` keeps both occurrences exactly where they already
        are and records only a fixed assembly relationship.
        """
        if not isinstance(target, ModelInstance):
            raise TypeError("component attach target must be another model object")
        if as_built:
            if (
                parent != Anchor.RIGHT
                or child != Anchor.LEFT
                or tuple(offset) != (0, 0)
                or gap != 0
                or angle is not None
            ):
                raise ValueError(
                    "as-built attach does not take anchors, offset, gap or angle"
                )
            return replace(
                self,
                attachment=Attachment(
                    target=target,
                    parent=None,
                    child=None,
                    offset=(0.0, 0.0),
                    as_built=True,
                ),
            )
        parent = _resolve_anchor_reference(target, parent)
        child = _resolve_anchor_reference(self, child)
        if parent is Anchor.INNER_BOTTOM or child is Anchor.INNER_BOTTOM:
            raise ValueError("Anchor.INNER_BOTTOM is not an assembly face anchor")
        if not isinstance(offset, (tuple, list)) or len(offset) != 2:
            raise ValueError("component attach offset must be an (u, v) pair")
        face_offset = tuple(offset)
        face_offset_values = tuple(pv(value) for value in face_offset)
        if not all(isfinite(value) for value in face_offset_values):
            raise ValueError("component attach offset must be finite")

        gap_value = pv(gap)
        if not isfinite(gap_value):
            raise ValueError("component attach gap must be finite")

        target_local = _anchor_local_point(target, parent)
        child_local = _anchor_local_point(self, child)

        tangent = (0.0, 0.0, 0.0)
        normal = (0.0, 0.0, 0.0)
        if parent in (
            Anchor.LEFT,
            Anchor.RIGHT,
            Anchor.FRONT,
            Anchor.BACK,
            Anchor.TOP,
            Anchor.BOTTOM,
            Anchor.CENTER,
        ):
            tangent = _face_offset(parent, face_offset_values)
            if parent is not Anchor.CENTER:
                normal = parent.vector

        target_world = tuple(
            target_local[i]
            + target.translation[i]
            + tangent[i]
            + normal[i] * gap_value
            for i in range(3)
        )
        translation = tuple(
            target_world[i] - child_local[i]
            for i in range(3)
        )
        angle_value = None
        if angle is not None:
            angle_value = pv(angle)
            if not isfinite(angle_value):
                raise ValueError("component attach angle must be finite")

        return replace(
            self,
            translation=translation,
            attachment=Attachment(
                target=target,
                parent=parent,
                child=child,
                offset=face_offset,
                gap=gap,
                angle=angle_value,
            ),
        )

    def __add__(self, other):
        return Assembly((self,)) + other

    __or__ = __add__


@dataclass(frozen=True)
class AssemblyAnchor:
    """Named attachment reference owned by an assembly.

    The target occurrence remains the real SolidCraft attachment target; the
    reference is a standard/direct component anchor interpreted in that
    occurrence. This lets an assembly expose semantic datums without putting
    application-specific anchors on the reusable component definition.
    """

    target: ModelInstance
    reference: Anchor | str | AnchorFrame | AnchorTopology
    offset: tuple[object, object] = (0, 0)


@dataclass(frozen=True)
class Assembly:
    """Ordered collection of reusable model occurrences."""

    instances: tuple[ModelInstance, ...]
    anchors: tuple[tuple[str, AssemblyAnchor], ...] = ()

    def group(self, name):
        """Wrap these occurrences in a real nested native component."""
        grouped = tuple(instance.group(name) for instance in self.instances)
        remap = {
            id(original): replacement
            for original, replacement in zip(self.instances, grouped)
        }
        anchors = tuple(
            (
                anchor_name,
                AssemblyAnchor(
                    target=remap[id(anchor.target)],
                    reference=anchor.reference,
                    offset=anchor.offset,
                ),
            )
            for anchor_name, anchor in self.anchors
        )
        return Assembly(grouped, anchors)

    def with_anchor(self, name, target, reference, *, offset=(0, 0)):
        """Expose one named datum owned by this assembly.

        ``offset`` is an optional symbolic in-plane (u, v) correction that a
        consumer can pass through to ``attach(offset=...)``. Keeping it on the
        assembly lets a semantic datum depend on assembly parameters without
        putting that knowledge on the reusable component.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("assembly anchor name must be non-empty text")
        if any(existing == name for existing, _ in self.anchors):
            raise ValueError(f"assembly anchor {name!r} already exists")
        if not isinstance(target, ModelInstance):
            raise TypeError("assembly anchor target must be a model object")
        if not any(instance is target for instance in self.instances):
            raise ValueError("assembly anchor target must belong to this assembly")
        if not isinstance(offset, (tuple, list)) or len(offset) != 2:
            raise ValueError("assembly anchor offset must be an (u, v) pair")
        if not all(isfinite(pv(value)) for value in offset):
            raise ValueError("assembly anchor offset must be finite")
        resolved = _resolve_anchor_reference(target, reference)
        return replace(
            self,
            anchors=self.anchors + (
                (
                    name,
                    AssemblyAnchor(
                        target=target,
                        reference=resolved,
                        offset=tuple(offset),
                    ),
                ),
            ),
        )

    def anchor(self, name):
        """Return one named assembly-owned attachment datum."""
        matches = [anchor for anchor_name, anchor in self.anchors
                   if anchor_name == name]
        if len(matches) != 1:
            raise KeyError(f"assembly has no unique anchor named {name!r}")
        return matches[0]

    def resolve(self, name):
        """Return one explicitly named occurrence."""
        matches = [instance for instance in self.instances if instance.name == name]
        if len(matches) != 1:
            raise KeyError(f"assembly has no unique object named {name!r}")
        return matches[0]

    def __getattr__(self, name):
        matches = [instance for instance in self.instances if instance.name == name]
        if len(matches) == 1:
            return matches[0]
        raise AttributeError(name)

    def __post_init__(self):
        if not self.instances:
            raise ValueError("assembly must contain at least one model instance")
        if not all(isinstance(item, ModelInstance) for item in self.instances):
            raise TypeError("assembly items must be model instances")

        names = [instance.name for instance in self.instances if instance.name is not None]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                "assembly object names must be unique: " + ", ".join(duplicates)
            )

        anchor_names = [name for name, _ in self.anchors]
        duplicate_anchors = sorted({
            name for name in anchor_names if anchor_names.count(name) > 1
        })
        if duplicate_anchors:
            raise ValueError(
                "assembly anchor names must be unique: "
                + ", ".join(duplicate_anchors)
            )
        for name, anchor in self.anchors:
            if not isinstance(anchor, AssemblyAnchor):
                raise TypeError(f"assembly anchor {name!r} is invalid")
            if not any(instance is anchor.target for instance in self.instances):
                raise ValueError(
                    f"assembly anchor {name!r} target is not in this assembly"
                )

    def __add__(self, other):
        if isinstance(other, ModelInstance):
            return Assembly(self.instances + (other,), self.anchors)
        if isinstance(other, Assembly):
            return Assembly(
                self.instances + other.instances,
                self.anchors + other.anchors,
            )
        return NotImplemented

    __or__ = __add__
