"""The shape comparator the contract tests judge every route with.

Its expectations are worked by hand from the rules in `contract_shapes.py`'s docstring.
"""

from contract_shapes import conforms, shape_of, shape_of_spec


def test_a_matching_answer_has_no_mismatch() -> None:
    golden = shape_of({"a": 1, "b": "x", "c": [1, 2], "d": None})
    assert conforms({"a": 7, "b": "y", "c": [], "d": None}, golden) == []


def test_a_missing_key_is_named_with_its_path() -> None:
    golden = shape_of({"a": {"b": 1, "c": 2}})
    assert conforms({"a": {"b": 1}}, golden) == ["a: missing key `c`"]


def test_an_extra_key_is_named_with_its_path() -> None:
    golden = shape_of({"a": 1})
    assert conforms({"a": 1, "z": 2}, golden) == ["$: unexpected key `z`"]


def test_a_wrong_type_names_both_types() -> None:
    golden = shape_of({"n": 1})
    assert conforms({"n": "1"}, golden) == ["n: expected number, got string"]


def test_an_integer_and_a_float_are_both_numbers_and_a_boolean_is_not() -> None:
    golden = shape_of({"n": 1.5})
    assert conforms({"n": 2}, golden) == []
    assert conforms({"n": True}, golden) == ["n: expected number, got boolean"]


def test_null_is_refused_where_the_golden_never_had_it() -> None:
    golden = shape_of({"n": 1})
    assert conforms({"n": None}, golden) == ["n: expected number, got null"]


def test_the_elements_of_a_list_are_merged_so_an_optional_key_may_be_absent() -> None:
    golden = shape_of({"rows": [{"id": 1, "note": "x"}, {"id": 2}]})
    assert conforms({"rows": [{"id": 3}, {"id": 4, "note": "y"}]}, golden) == []
    assert conforms({"rows": [{"note": "y"}]}, golden) == ["rows[0]: missing key `id`"]


def test_a_value_null_in_one_element_and_text_in_another_is_nullable_text() -> None:
    golden = shape_of([{"v": None}, {"v": "x"}])
    assert conforms([{"v": "a"}, {"v": None}], golden) == []
    assert conforms([{"v": 3}], golden) == ["[0].v: expected string or null, got number"]


def test_an_empty_golden_list_accepts_any_elements() -> None:
    assert conforms({"x": [1, "a", {"k": 1}]}, shape_of({"x": []})) == []


def test_keys_must_keep_the_goldens_relative_order() -> None:
    golden = shape_of({"a": 1, "b": 2, "c": 3})
    assert conforms({"a": 1, "c": 3, "b": 2}, golden) == ["$: keys out of order: `c` before `b`"]


def test_a_map_with_dynamic_keys_checks_every_value_against_one_shape() -> None:
    golden = shape_of({"s-1": {"cost": 1}, "s-2": {"cost": 2}}, maps=("$",))
    assert conforms({"other": {"cost": 5}, "x": {"cost": 0.5}}, golden) == []
    assert conforms({"other": {"cost": "5"}}, golden) == ["other.cost: expected number, got string"]


def test_a_hand_spec_names_types_optional_keys_and_nulls() -> None:
    spec = shape_of_spec({"notice": str, "undo": str | None, "id?": str})
    assert conforms({"notice": "", "undo": None}, spec) == []
    assert conforms({"notice": "", "undo": "t", "id": "CF-1"}, spec) == []
    assert conforms({"notice": ""}, spec) == ["$: missing key `undo`"]
    assert conforms({"notice": "", "undo": 1}, spec) == [
        "undo: expected string or null, got number"
    ]
