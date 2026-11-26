"""Names of the tests a source file defines, read with regular expressions (no parser)."""

import ast
import re

# `\s` and `\w` of a `str` pattern are `isspace` and `isalnum` or `_`, the classes the previous
# reader used.
_DEFINITION = re.compile(r"(?:async\s+)?(?:def|fn|func)\s+(\w+)\s*\(")
_VITEST = re.compile(r"""(?:it|test)\(\s*['"](\w+)['"]""")
_ATTRIBUTE_PATH = re.compile(r"[^(\]]*")
_PYTHON_NAME = re.compile(r"\w+")
_RUST_FN = re.compile(r"(?:pub(?:\([^)]*\))?\s+)?(?:(?:async|const|unsafe)\s+)*fn\s+(\w+)\s*[(<]")


def _name_at(line: str) -> str | None:
    """The name a definition or Vitest test declares at the start of `line`, else None."""
    body = line.lstrip()
    for pattern in (_DEFINITION, _VITEST):
        found = pattern.match(body)
        if found is not None:
            return str(found.group(1))
    return None


def defined_functions(text: str) -> list[str]:
    """The names declared at a line start.

    These are `def`, `fn` and `func` (after an optional `async`) and Vitest's `it('name'` and
    `test("name"`. One declaration per line; a definition in the middle of a line is not read.
    """
    names = []
    for line in text.split("\n"):
        name = _name_at(line)
        if name is not None:
            names.append(name)
    return names


def rust_tests(text: str) -> list[str]:
    """The functions marked `#[test]` or an attribute whose path ends in `::test`.

    Attributes are read across doc comments, blank lines and attributes of several lines.
    """
    names: list[str] = []
    marked = open_attribute = False
    for raw in text.splitlines():
        line = raw.strip()
        if open_attribute:
            open_attribute = "]" not in line
            continue
        if line.startswith("#["):
            path = _ATTRIBUTE_PATH.match(line[2:])
            path_text = path.group(0).strip() if path else ""
            marked = marked or path_text == "test" or path_text.endswith("::test")
            open_attribute = "]" not in line
            continue
        if not line or line.startswith("//"):
            continue
        found = _RUST_FN.match(line)
        name = found.group(1) if found else _name_at(line)
        if marked and name is not None:
            names.append(name)
        marked = False
    return names


def _walk(parent: ast.AST, classes: list[str], found: list[tuple[str, str]]) -> None:
    for node in ast.iter_child_nodes(parent):
        if isinstance(node, ast.ClassDef):
            _walk(node, [*classes, node.name], found)
        else:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found.append((node.name, "::".join([*classes, node.name])))
            _walk(node, classes, found)


def _scanned_nodes(text: str) -> list[tuple[str, str]]:
    """The same reading by indentation, for a file that is not valid Python."""
    classes: list[tuple[int, str]] = []
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        body = line.lstrip()
        if not body or body.startswith("#"):
            continue
        indent = len(line) - len(body)
        classes = [(depth, name) for depth, name in classes if depth < indent]
        if body.startswith("class "):
            name = _PYTHON_NAME.match(body[len("class ") :])
            classes.append((indent, name.group(0) if name else ""))
            continue
        definition = body.removeprefix("async ").lstrip()
        if definition.startswith("def "):
            name = _PYTHON_NAME.match(definition[len("def ") :])
            if name is not None:
                node = "::".join([*(cls for _, cls in classes), name.group(0)])
                found.append((name.group(0), node))
    return found


def python_nodes(text: str) -> list[tuple[str, str]]:
    """Each Python function as `(name, pytest node)`: `Class::name` for a method.

    The file is parsed, so a docstring or a continued signature at column zero does not end a
    class. A file that does not parse is read by indentation instead.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError, ValueError:
        return _scanned_nodes(text)
    found: list[tuple[str, str]] = []
    _walk(tree, [], found)
    return found
