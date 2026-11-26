from code_factory.platform.text import defined_functions, python_nodes, rust_tests


def test_defined_functions_finds_the_declaration_forms() -> None:
    text = (
        "def a(x):\nasync def b (x):\nfn c() {}\nfunc d() {}\n"
        "it('e', () => {})\ntest(\"f\", () => {})\n"
    )
    assert defined_functions(text) == ["a", "b", "c", "d", "e", "f"]


def test_defined_functions_skips_lookalikes_and_mid_line_definitions() -> None:
    assert defined_functions("define x(\nx = 1; def y(\nundefined(\n") == []


def test_defined_functions_reads_an_indented_method() -> None:
    assert defined_functions("class A:\n    def m(self):\n        pass\n") == ["m"]


def test_python_nodes_name_methods_with_their_class_and_reset_after_dedent() -> None:
    text = (
        "def top():\n    pass\n\nclass A:\n    def one(self):\n        pass\n\n"
        "    async def two(self):\n        pass\n\ndef after():\n    pass\n"
    )
    assert python_nodes(text) == [
        ("top", "top"),
        ("one", "A::one"),
        ("two", "A::two"),
        ("after", "after"),
    ]


def test_rust_tests_read_attributes_across_comments_blanks_and_lines() -> None:
    text = (
        "#[test]\nfn plain() {}\n\n"
        "#[tokio::test]\n/// doc\n\nasync fn awaited() {}\n\n"
        '#[test]\n#[should_panic(\n    expected = "x"\n)]\nfn multi() {}\n\n'
        "fn unmarked() {}\n"
    )
    assert rust_tests(text) == ["plain", "awaited", "multi"]


def test_an_attribute_that_is_not_a_test_marks_nothing() -> None:
    assert rust_tests("#[derive(Debug)]\nfn f() {}\n#[cfg(test)]\nfn g() {}\n") == []


def test_a_docstring_line_at_column_zero_does_not_end_the_class() -> None:
    text = (
        "class TestExample:\n    def test_one(self):\n        '''doc\nat column zero\n'''\n\n"
        "    def test_two(self):\n        pass\n"
    )
    assert python_nodes(text) == [
        ("test_one", "TestExample::test_one"),
        ("test_two", "TestExample::test_two"),
    ]


def test_a_signature_continued_at_column_zero_keeps_its_class() -> None:
    text = (
        "class TestExample:\n    def test_one(\nself,\n    ):\n        pass\n"
        "    def test_two(self): ...\n"
    )
    assert python_nodes(text) == [
        ("test_one", "TestExample::test_one"),
        ("test_two", "TestExample::test_two"),
    ]


def test_rust_tests_take_visibility_and_qualifier_prefixes() -> None:
    text = (
        "#[test]\npub fn a() {}\n#[test]\npub(crate) async fn b() {}\n#[test]\nunsafe fn c() {}\n"
    )
    assert rust_tests(text) == ["a", "b", "c"]


def test_a_file_that_does_not_parse_is_read_by_indentation() -> None:
    text = "class A:\n    def m(self) pass\n    def n(self): ...\ndef top(): ...\n"
    assert python_nodes(text) == [("m", "A::m"), ("n", "A::n"), ("top", "top")]
