"""Starting a split: a run of stage split, asked to file the brief's pieces as child tickets."""

from code_factory.runs.rules.split import split_prompt


def test_the_prompt_names_the_parent_the_brief_and_the_tool_to_file_with() -> None:
    prompt = split_prompt("CF-3", "Checkout", "", "  Cards.  ")
    assert "create_ticket" in prompt
    assert prompt.endswith("The parent ticket is CF-3: Checkout\n\nThe brief:\n\nCards.\n")
