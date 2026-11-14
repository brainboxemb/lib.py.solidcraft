"""Execute a trusted SCPF model and compile it to native SolidCraft commands.

A script may end with an explicit model call such as Plate(). If the file
instead defines exactly one public class with build(), that class is used as
the root model automatically. This lets reusable component source files run
standalone without a launcher or duplicate model definition.

Within build() or a final model function, a last geometry expression acts as
an implicit return. No show() or main() is required.
"""
import ast
from contextlib import contextmanager
from dataclasses import dataclass, is_dataclass
import functools
import inspect
from pathlib import Path
import sys
import warnings

from . import core
from .compiler import compile_model
from .core import Expression, Parameter, Shape, command_value, parameters_in, pv
from .assembly import compile_assembly
from .model_objects import Assembly, ModelDefinition, ModelInstance
from .history import History, behavior
from .explicit_sketch import Sketch


class ModelParameterWarning(UserWarning):
    """A declared editable model parameter lost its native CAD dependency."""


@dataclass(frozen=True)
class _BuiltDesign:
    result: object
    parameters: tuple[tuple[str, float], ...]


def _warn_missing_model_parameters(
    parameters, commands, *, context="model", flattened_parameters=()
):
    """Warn when declared model parameters are lost or only partly native."""
    native = {
        command["params"]["name"]
        for command in commands
        if command["command"] == "parameters.add"
    }
    flattened = set(flattened_parameters)

    for name, _ in parameters:
        if name in flattened:
            if name in native:
                detail = (
                    "remains native in some geometry, but occurrence placement "
                    "also consumes it as a concrete Python value. Changing the "
                    "SolidCraft parameter will therefore update only part of "
                    "the model."
                )
            else:
                detail = (
                    "has no native SolidCraft dependency because occurrence "
                    "placement consumes it as a concrete Python value."
                )
            warnings.warn(
                f"{context} parameter {name!r} {detail} Preserve the symbolic "
                "relationship in native geometry/placement, or rename it to "
                f"_{name} if it is intentionally Forge/build-time.",
                ModelParameterWarning,
                stacklevel=3,
            )
        elif name not in native:
            warnings.warn(
                f"{context} parameter {name!r} has no native SolidCraft "
                "dependency; it may have been consumed as a Python value "
                "(for example via pv()). Preserve the symbolic value, or "
                f"rename it to _{name} if it is intentionally Forge/build-time.",
                ModelParameterWarning,
                stacklevel=3,
            )


def _symbolic(value, name):
    """Promote numeric model inputs to named CAD parameters."""
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return Parameter(name, value)
    return value


def _model_function(function):
    """Call a function-based model with named symbolic CAD dimensions."""
    signature = inspect.signature(function)

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        for name, value in bound.arguments.items():
            bound.arguments[name] = _symbolic(value, name)
        return function(*bound.args, **bound.kwargs)

    return wrapped


def _plain_model_fields(cls):
    """Ordered numeric model/build fields, excluding UPPER_CASE constants.

    Naming is intentional:
      lower_case   -> editable native model parameter
      _lower_case  -> Forge/build-time input, never a native parameter
      UPPER_CASE   -> fixed class constant, not a model input
    """
    fields = {}
    # Base model dimensions come first; subclasses may override defaults
    # without reimplementing build(). Existing key order stays stable.
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        for name, value in vars(base).items():
            if (name.startswith("__")
                    or name.isupper()
                    or not isinstance(value, (int, float))
                    or isinstance(value, bool)):
                continue
            fields[name] = value
    return list(fields.items())


def _plain_reference_fields(cls):
    """Ordered non-parametric object inputs declared with a None default.

    These values are passed through to build() unchanged. They are intended
    for assembly/component references such as an already-built WoodFrame and
    never become SolidCraft parameters.
    """
    fields = {}
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        for name, value in vars(base).items():
            if (
                name.startswith("__")
                or name.isupper()
                or value is not None
            ):
                continue
            fields[name] = value
    return list(fields.items())


def _parameter_input(value, name, *, build_only=False):
    """Bind one input while preserving implicit parameter intent.

    Public numeric inputs become editable native parameters. Private
    underscore-prefixed numeric inputs stay concrete Forge/build inputs.
    Passing an existing Parameter/Expression into either kind preserves the
    inherited symbolic dependency instead of creating a duplicate child
    parameter.
    """
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a numeric model parameter")

    if build_only:
        if isinstance(value, (Parameter, Expression)):
            external = tuple((p.name, p.value) for p in parameters_in(value))
            return pv(value), value, external, (name, command_value(value)), False
        if isinstance(value, (int, float)):
            concrete = float(value)
            return concrete, concrete, (), None, True
        raise TypeError(f"{name} must be a numeric Forge/build parameter")

    if isinstance(value, (Parameter, Expression)):
        external = tuple((p.name, p.value) for p in parameters_in(value))
        return pv(value), value, external, (name, command_value(value)), False

    if isinstance(value, (int, float)):
        concrete = float(value)
        return concrete, Parameter(name, concrete), (), None, False

    raise TypeError(f"{name} must be a numeric model parameter")

def _plain_model_data(cls, *args, **kwargs):
    """Instantiate a plain model and classify public vs fixed inputs."""
    fields = _plain_model_fields(cls)
    references = _plain_reference_fields(cls)
    names = [name for name, _ in fields]
    reference_names = [name for name, _ in references]
    if len(args) > len(fields):
        raise TypeError(
            f"{cls.__name__}() takes at most {len(fields)} positional model arguments"
        )

    values = dict(fields)
    reference_values = dict(references)
    assigned = set()
    for (name, _), value in zip(fields, args):
        values[name] = value
        assigned.add(name)

    for name, value in kwargs.items():
        if name in reference_values:
            if name in assigned:
                raise TypeError(
                    f"{cls.__name__}() got multiple values for input {name!r}"
                )
            reference_values[name] = value
            assigned.add(name)
            continue
        if name not in values:
            raise TypeError(
                f"{cls.__name__}() got an unexpected model input {name!r}"
            )
        if name in assigned:
            raise TypeError(
                f"{cls.__name__}() got multiple values for parameter {name!r}"
            )
        values[name] = value
        assigned.add(name)

    instance = cls()
    for name in reference_names:
        object.__setattr__(instance, name, reference_values[name])

    concrete = []
    fixed = []
    external = {}
    bindings = []
    for name in names:
        build_only = name.startswith("_")
        value, symbolic, inherited, binding, is_fixed = _parameter_input(
            values[name],
            name,
            build_only=build_only,
        )
        if binding is None:
            if is_fixed:
                fixed.append((name, value))
            else:
                concrete.append((name, value))
        else:
            bindings.append(binding)
            for parameter_name, parameter_value in inherited:
                previous = external.setdefault(parameter_name, parameter_value)
                if previous != parameter_value:
                    raise ValueError(
                        f"conflicting inherited parameter {parameter_name!r}"
                    )
        object.__setattr__(instance, name, symbolic)
    return (
        instance,
        tuple(concrete),
        tuple(fixed),
        tuple(external.items()),
        tuple(bindings),
    )


def _plain_model_instance(cls, *args, **kwargs):
    """Instantiate a plain SCPF model class without requiring @dataclass."""
    return _plain_model_data(cls, *args, **kwargs)[0]


def _parameterized_instance(cls, *args, **kwargs):
    """Construct one model object and classify its reusable inputs."""
    if not is_dataclass(cls):
        return _plain_model_data(cls, *args, **kwargs)

    instance = cls(*args, **kwargs)
    signature = inspect.signature(cls)
    bound = signature.bind(*args, **kwargs)
    bound.apply_defaults()
    concrete = []
    fixed = []
    external = {}
    bindings = []
    for name, value in bound.arguments.items():
        if name not in vars(instance):
            continue
        if isinstance(value, (int, float, Parameter, Expression)) and not isinstance(value, bool):
            build_only = name.startswith("_")
            number, symbolic, inherited, binding, is_fixed = _parameter_input(
                value,
                name,
                build_only=build_only,
            )
            if binding is None:
                if is_fixed:
                    fixed.append((name, number))
                else:
                    concrete.append((name, number))
            else:
                bindings.append(binding)
                for parameter_name, parameter_value in inherited:
                    previous = external.setdefault(parameter_name, parameter_value)
                    if previous != parameter_value:
                        raise ValueError(
                            f"conflicting inherited parameter {parameter_name!r}"
                        )
            object.__setattr__(instance, name, symbolic)
    return (
        instance,
        tuple(concrete),
        tuple(fixed),
        tuple(external.items()),
        tuple(bindings),
    )


def _component_anchor_frames(instance):
    """Read optional named local attachment frames from one component model."""
    provider = getattr(instance, "anchors", None)
    if provider is None:
        return ()
    value = provider() if callable(provider) else provider
    if not isinstance(value, dict):
        raise TypeError("component anchors must be returned as a dict")

    anchors = []
    standard_names = {anchor.value for anchor in core.Anchor}
    for name, frame in value.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError(
                "component anchor names must be valid Python identifiers"
            )
        if name in standard_names:
            raise ValueError(
                f"component anchor {name!r} conflicts with a standard Anchor"
            )
        if not isinstance(frame, (core.AnchorFrame, core.AnchorTopology)):
            raise TypeError(
                f"component anchor {name!r} must be an AnchorFrame "
                "or AnchorTopology"
            )
        anchors.append((name, frame))
    return tuple(anchors)


def _build_object(cls, *args, **kwargs):
    """Build one user model and return its classified reusable inputs."""
    instance, concrete, fixed, external, bindings = _parameterized_instance(
        cls, *args, **kwargs
    )
    build = getattr(instance, "build", None)
    if not callable(build):
        raise TypeError(f"{cls.__name__} must define build()")
    result = build()
    anchors = _component_anchor_frames(instance)
    return result, concrete, fixed, external, bindings, anchors


def _design_object(cls, *args, **kwargs):
    """Build the root model and retain its declared native parameters."""
    result, concrete, _, _, _, _ = _build_object(cls, *args, **kwargs)
    if not isinstance(result, (Shape, ModelInstance, Assembly)):
        raise TypeError(
            f"{cls.__name__}.build() must finish with a Shape or assembly"
        )
    return _BuiltDesign(result=result, parameters=concrete)


def _reusable_model_object(cls, *args, **kwargs):
    """Build a nested user model as a reusable component definition."""
    object_name = kwargs.pop("name", None)
    if object_name is not None:
        if (
            not isinstance(object_name, str)
            or not object_name.isidentifier()
            or object_name.startswith("_")
        ):
            raise ValueError(
                "component object name must be a public Python identifier"
            )

    result, concrete, fixed, external, bindings, anchors = _build_object(
        cls, *args, **kwargs
    )
    if not isinstance(result, Shape):
        raise TypeError(
            f"{cls.__name__}.build() must produce one Shape when reused as a component"
        )
    return ModelInstance(
        ModelDefinition(
            class_name=cls.__name__,
            parameters=concrete,
            shape=result,
            fixed_inputs=fixed,
            external_parameters=external,
            input_bindings=bindings,
            anchors=anchors,
        ),
        name=object_name,
    )


def _model_factory(cls):
    """Replace a nested class name with a transparent reusable-model factory."""
    @functools.wraps(cls)
    def factory(*args, **kwargs):
        return _reusable_model_object(cls, *args, **kwargs)

    factory._scpf_component_class = cls
    return factory


def component(cls):
    """Declare a reusable component with implicit editable public parameters.

    Public lower-case numeric fields become component-local editable native
    parameters automatically. Passing a parent Parameter/Expression into a
    component input preserves that existing dependency and does not create a
    duplicate child parameter. Private underscore-prefixed defaults remain
    Forge/build-time inputs.
    """
    if not isinstance(cls, type) or not callable(getattr(cls, "build", None)):
        raise TypeError("component() expects a model class with build()")
    return _model_factory(cls)

def _reusable_assembly_object(cls, *args, **kwargs):
    """Build an imported assembly class without exposing build_* helpers."""
    result, _, _, _, _, _ = _build_object(cls, *args, **kwargs)
    if not isinstance(result, (ModelInstance, Assembly)):
        raise TypeError(
            f"{cls.__name__}.build() must produce a component or assembly"
        )
    return result


def _assembly_factory(cls):
    @functools.wraps(cls)
    def factory(*args, **kwargs):
        return _reusable_assembly_object(cls, *args, **kwargs)
    factory._scpf_assembly_class = cls
    return factory


def assembly(cls):
    """Declare an imported class whose build() returns an SCPF assembly."""
    if not isinstance(cls, type) or not callable(getattr(cls, "build", None)):
        raise TypeError("assembly() expects a model class with build()")
    return _assembly_factory(cls)


def _implicit_shape(body):
    """Turn a trailing expression into an implicit return.

    This is a deliberate SCPF model convention; do not rewrite nested
    helper methods or unrelated Python functions. Explicit return stays
    valid. A last assignment alone is not treated as a CAD result.
    """
    if body and isinstance(body[-1], ast.Expr):
        body[-1] = ast.copy_location(ast.Return(value=body[-1].value), body[-1])


@contextmanager
def _model_import_context(path: Path):
    """Make project-local component imports available for a model script.

    A script in `<project>/models/<slug>/scpf/model.py` may import
    `models.components.*`. This must work whether the user runs SCPF from
    the repository root or from the script's own directory.

    Only the execution of this trusted script receives these import paths.
    Restore sys.path afterwards; do not require user-set PYTHONPATH.
    """
    roots = [path.parent]
    for ancestor in path.parents:
        if ancestor.name == "models":
            roots.append(ancestor.parent)
            break

    original = sys.path[:]
    original_dont_write_bytecode = sys.dont_write_bytecode
    try:
        # Model projects often split parts and assemblies over small Python
        # modules. Keep those source trees clean: imported model modules are
        # transient build input and do not need adjacent __pycache__ files.
        sys.dont_write_bytecode = True
        for root in reversed(roots):
            folder = str(root)
            if folder in sys.path:
                sys.path.remove(folder)
            sys.path.insert(0, folder)
        yield
    finally:
        sys.path[:] = original
        sys.dont_write_bytecode = original_dont_write_bytecode


def run_script(path: str | Path) -> dict:
    """Run a trusted SCPF script and return its native command document."""
    path = Path(path).resolve()
    syntax = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    explicit_root = (
        bool(syntax.body)
        and isinstance(syntax.body[-1], ast.Expr)
        and isinstance(syntax.body[-1].value, ast.Call)
        and isinstance(syntax.body[-1].value.func, ast.Name)
    )

    if explicit_root:
        last = syntax.body.pop()
        name = last.value.func.id
    else:
        # A reusable component file should also be a valid standalone model.
        # Auto-select only when the choice is unambiguous: exactly one public
        # top-level class that defines build(). Never guess between models.
        candidates = []
        for item in syntax.body:
            if not isinstance(item, ast.ClassDef) or item.name.startswith("_"):
                continue
            if any(
                isinstance(member, ast.FunctionDef) and member.name == "build"
                for member in item.body
            ):
                candidates.append(item)

        if len(candidates) != 1:
            names = ", ".join(item.name for item in candidates) or "none"
            raise SyntaxError(
                "SCPF needs an explicit final model call unless the file "
                "defines exactly one public class with build(); "
                f"candidates: {names}"
            )

        name = candidates[0].name
        last = ast.Expr(
            value=ast.Call(
                func=ast.Name(id=name, ctx=ast.Load()),
                args=[],
                keywords=[],
            )
        )
        ast.fix_missing_locations(last)

    definitions = {
        item.name: item for item in syntax.body
        if isinstance(item, (ast.FunctionDef, ast.ClassDef))
    }
    definition = definitions.get(name)

    context = {
        "__name__": "__scpf_model__",
        "__file__": str(path.resolve()),
        "dataclass": dataclass,
        "Box": core.Box,
        "Cylinder": core.Cylinder,
        "Hole": core.Hole,
        "Lip": core.Lip,
        "SnapFit": core.SnapFit,
        "Boss": core.Boss,
        "Rest": core.Rest,
        "Depth": core.Depth,
        "Sphere": core.Sphere,
        "Polygon2D": core.Polygon2D,
        "Rectangle2D": core.Rectangle2D,
        "RoundedRectangle2D": core.RoundedRectangle2D,
        "Circle2D": core.Circle2D,
        "Text2D": core.Text2D,
        "Direction": core.Direction,
        "Edges": core.Edges,
        "Faces": core.Faces,
        "Anchor": core.Anchor,
        "AnchorFrame": core.AnchorFrame,
        "AnchorTopology": core.AnchorTopology,
        "Axis": core.Axis,
        "Shape": core.Shape,
        "half": core.half,
        "midpoint": core.midpoint,
        "pv": core.pv,
        "X": core.X,
        "Y": core.Y,
        "Z": core.Z,
        "History": History,
        "behavior": behavior,
        "Sketch": Sketch,
    }
    if isinstance(definition, ast.FunctionDef):
        _implicit_shape(definition.body)

    model_classes = {}
    for item in syntax.body:
        if not isinstance(item, ast.ClassDef):
            continue
        build_method = next(
            (member for member in item.body
             if isinstance(member, ast.FunctionDef) and member.name == "build"),
            None,
        )
        if build_method is not None:
            _implicit_shape(build_method.body)
            model_classes[item.name] = item

    ast.fix_missing_locations(syntax)
    with _model_import_context(path):
        exec(compile(syntax, str(path), "exec"), context)

        root_object = context.get(name)
        root_component_class = getattr(
            root_object, "_scpf_component_class", None
        )
        root_assembly_class = getattr(
            root_object, "_scpf_assembly_class", None
        )
        root_is_class = isinstance(root_object, type)
        root_is_component = root_component_class is not None
        root_is_assembly = root_assembly_class is not None
        for class_name in model_classes:
            if class_name == name:
                continue
            model_object = context[class_name]
            if (
                getattr(model_object, "_scpf_component_class", None) is not None
                or getattr(model_object, "_scpf_assembly_class", None) is not None
            ):
                continue
            context[class_name] = _model_factory(model_object)

        if isinstance(definition, ast.FunctionDef):
            context[name] = _model_function(context[name])
            result = eval(
                compile(ast.Expression(body=last.value), str(path), "eval"), context
            )
        elif root_is_class or root_is_component:
            # A reusable @component source remains directly runnable as a
            # standalone design. Compile its original model class as the root
            # shape, while imported/nested uses keep the component factory.
            root_class = (
                root_object if root_is_class else root_component_class
            )
            constructor = ast.Call(
                func=ast.Name(id="_scpf_design_object", ctx=ast.Load()),
                args=[ast.Name(id="_scpf_root_class", ctx=ast.Load()), *last.value.args],
                keywords=last.value.keywords,
            )
            context["_scpf_design_object"] = _design_object
            context["_scpf_root_class"] = root_class
            ast.fix_missing_locations(constructor)
            built = eval(
                compile(ast.Expression(body=constructor), str(path), "eval"),
                context,
            )
            result = built.result
        elif root_is_assembly:
            result = eval(
                compile(ast.Expression(body=last.value), str(path), "eval"),
                context,
            )
        else:
            raise SyntaxError(
                f"the last call must use a defined function/class or "
                f"an imported model/component/assembly: {name}"
            )

    if isinstance(result, Shape):
        document = compile_model(result, name)
    elif isinstance(result, (ModelInstance, Assembly)):
        document = compile_assembly(result, name)
    else:
        raise TypeError(f"{name}() must produce CAD geometry or an assembly")

    if root_is_class or root_is_component:
        instances = (
            (result,)
            if isinstance(result, ModelInstance)
            else result.instances
            if isinstance(result, Assembly)
            else ()
        )
        flattened_parameters = {
            parameter_name
            for instance in instances
            for parameter_name in instance.flattened_parameters
        }
        _warn_missing_model_parameters(
            built.parameters,
            document["commands"],
            context=name,
            flattened_parameters=flattened_parameters,
        )
    return document
