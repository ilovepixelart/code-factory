"""Shapes of JSON answers, and the comparison the contract tests judge a route's answer with.

A shape is taken from a golden answer (`shape_of`) or written by hand (`shape_of_spec`). An answer
conforms when, at every path:

- its type is one the shape saw (`number` covers integers and floats; a boolean is not a number;
  `null` is accepted only where the shape saw it);
- an object has every key the shape saw in all of its examples, and no key it saw in none; the keys
  it has appear in the order the examples gave them;
- the elements of an array are merged into one shape first, so a key present in some elements and
  absent in others is optional; an array the golden shows empty accepts any elements;
- an object declared a map (dynamic keys, such as a session id) has every value checked against
  the one shape its values were merged into.

Values are never compared: a route answers the sample world, whose numbers and texts differ from
the golden's.
"""

from dataclasses import dataclass, field
from functools import reduce
from types import NoneType, UnionType
from typing import Any, get_args, get_origin

_ORDER = ("string", "number", "boolean", "array", "object", "null")


@dataclass(frozen=True)
class Map:
    """In a hand spec: an object whose keys are dynamic and whose values all have this spec."""

    value: Any


@dataclass
class Shape:
    """What one place of an answer may hold."""

    types: set[str]
    fields: dict[str, Shape] = field(default_factory=dict)
    required: set[str] = field(default_factory=set)
    order: list[str] = field(default_factory=list)
    item: Shape | None = None
    values: Shape | None = None


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _merge_order(first: list[str], second: list[str]) -> list[str]:
    merged = list(first)
    for index, key in enumerate(second):
        if key in merged:
            continue
        before = next((k for k in reversed(second[:index]) if k in merged), None)
        merged.insert(merged.index(before) + 1 if before is not None else 0, key)
    return merged


def merge(first: Shape, second: Shape) -> Shape:
    """One shape both examples conform to; a key missing from either becomes optional."""
    both_objects = "object" in first.types and "object" in second.types
    required = (
        first.required & second.required if both_objects else first.required | second.required
    )
    fields = dict(first.fields)
    for key, shape in second.fields.items():
        fields[key] = merge(fields[key], shape) if key in fields else shape
    return Shape(
        types=first.types | second.types,
        fields=fields,
        required=required,
        order=_merge_order(first.order, second.order),
        item=_merge_optional(first.item, second.item),
        values=_merge_optional(first.values, second.values),
    )


def _merge_optional(first: Shape | None, second: Shape | None) -> Shape | None:
    if first is None or second is None:
        return first or second
    return merge(first, second)


def _join(path: str, key: str) -> str:
    return key if path == "$" else f"{path}.{key}"


def _at(path: str, index: int) -> str:
    return f"{'' if path == '$' else path}[{index}]"


def _nullable(shape: Shape, wanted: bool) -> Shape:
    """The shape, accepting `null` too when the app's types say the field may be null."""
    return (
        Shape(
            shape.types | {"null"},
            shape.fields,
            shape.required,
            shape.order,
            shape.item,
            shape.values,
        )
        if wanted
        else shape
    )


def shape_of(
    value: Any,  # noqa: ANN401
    maps: tuple[str, ...] = (),
    path: str = "$",
    nullable: tuple[str, ...] = (),
) -> Shape:
    """The shape of a golden value; `maps` lists the paths of objects with dynamic keys.

    `nullable` names fields the app's types allow to be null though every golden example has a
    value (an object the golden always held).

    A path is written as an answer's mismatches write it: keys joined by `.`, `[]` for every
    array element, `$` for the whole answer.
    """
    name = _type_name(value)
    if name == "array":
        item = None
        for element in value:
            shape = shape_of(element, maps, f"{'' if path == '$' else path}[]", nullable)
            item = shape if item is None else merge(item, shape)
        return Shape({"array"}, item=item)
    if name != "object":
        return Shape({name})
    if path in maps:
        values = None
        for element in value.values():
            shape = shape_of(element, maps, _join(path, "*"), nullable)
            values = shape if values is None else merge(values, shape)
        return Shape({"object"}, values=values)
    fields = {
        key: _nullable(shape_of(element, maps, _join(path, key), nullable), key in nullable)
        for key, element in value.items()
    }
    return Shape({"object"}, fields, set(fields), list(fields))


_SCALARS = {str: "string", int: "number", float: "number", bool: "boolean", NoneType: "null"}


def _object_spec(spec: dict[str, Any]) -> Shape:
    fields: dict[str, Shape] = {}
    required: set[str] = set()
    for key, value in spec.items():
        name = key.removesuffix("?")
        fields[name] = shape_of_spec(value)
        if not key.endswith("?"):
            required.add(name)
    return Shape({"object"}, fields, required, list(fields))


def _union_spec(spec: UnionType) -> Shape:
    shapes = [shape_of_spec(part) for part in get_args(spec)]
    return reduce(merge, shapes)


def shape_of_spec(spec: Any) -> Shape:  # noqa: ANN401, PLR0911
    """The shape a hand-written spec states.

    `str`, `int`, `float`, `bool`, `None`, `Any`; unions with `|`; `list[X]` and `[X]`; a dict is an
    object whose key ending in `?` is optional; `Map(X)` is an object with dynamic keys.
    """
    if isinstance(spec, Shape):
        return spec
    if isinstance(spec, Map):
        return Shape({"object"}, values=shape_of_spec(spec.value))
    if isinstance(spec, dict):
        return _object_spec(spec)
    if isinstance(spec, UnionType):
        return _union_spec(spec)
    if isinstance(spec, list) or get_origin(spec) is list:
        items = spec if isinstance(spec, list) else get_args(spec)
        return Shape({"array"}, item=shape_of_spec(items[0]) if items else None)
    if spec is Any:
        return Shape({"any"})
    return Shape({_SCALARS[NoneType if spec is None else spec]})


def _expected(types: set[str]) -> str:
    return " or ".join(name for name in _ORDER if name in types)


def conforms(value: Any, shape: Shape, path: str = "$") -> list[str]:  # noqa: ANN401
    """Every way `value` departs from `shape`, each as `<path>: <what>`; empty when it conforms."""
    if "any" in shape.types:
        return []
    name = _type_name(value)
    if name not in shape.types:
        return [f"{path}: expected {_expected(shape.types)}, got {name}"]
    if name == "array":
        if shape.item is None:
            return []
        return [
            problem
            for index, element in enumerate(value)
            for problem in conforms(element, shape.item, _at(path, index))
        ]
    if name == "object":
        return _object_problems(value, shape, path)
    return []


def _object_problems(value: dict[str, Any], shape: Shape, path: str) -> list[str]:
    if shape.values is not None:
        return [
            problem
            for key, element in value.items()
            for problem in conforms(element, shape.values, _join(path, key))
        ]
    problems = [f"{path}: unexpected key `{key}`" for key in value if key not in shape.fields]
    problems += [
        f"{path}: missing key `{key}`"
        for key in shape.order
        if key in shape.required and key not in value
    ]
    problems += _order_problems(value, shape, path)
    for key, element in value.items():
        if key in shape.fields:
            problems += conforms(element, shape.fields[key], _join(path, key))
    return problems


def _order_problems(value: dict[str, Any], shape: Shape, path: str) -> list[str]:
    rank = {key: index for index, key in enumerate(shape.order)}
    seen = [key for key in value if key in rank]
    latest = None
    for key in seen:
        if latest is not None and rank[key] < rank[latest]:
            return [f"{path}: keys out of order: `{latest}` before `{key}`"]
        latest = key if latest is None or rank[key] > rank[latest] else latest
    return []
