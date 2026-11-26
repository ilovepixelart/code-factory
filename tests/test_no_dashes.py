from repo_files import repo_files, text_lines

# Built from code points so this file holds neither character.
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def test_no_file_name_or_content_holds_an_em_or_en_dash() -> None:
    found = []
    for path in repo_files():
        if EM_DASH in str(path) or EN_DASH in str(path):
            found.append(f"{path}: in the file name")
        found.extend(
            f"{path}:{number}"
            for number, line in enumerate(text_lines(path), start=1)
            if EM_DASH in line or EN_DASH in line
        )
    assert not found, "em and en dashes are not used here; use commas, colons or parentheses:\n" + (
        "\n".join(found)
    )
