import pytest

from src.core.characters import read_characters, save_characters, validate_character_name


def test_round_trips_names_and_shortcuts(tmp_path):
    path = str(tmp_path / "characters.txt")
    characters = [{"name": "Monica", "key": "1"}, {"name": "Joey", "key": None}]

    save_characters(path, characters)

    assert read_characters(path) == characters


def test_missing_file_yields_no_characters(tmp_path):
    assert read_characters(str(tmp_path / "absent.txt")) == []


@pytest.mark.parametrize("name", ["Sheldon", "Dr. Cooper", "Mary Cooper"])
def test_accepts_plain_names(name):
    assert validate_character_name(name) is None


@pytest.mark.parametrize("name", ["", "   ", "Cooper, Sheldon"])
def test_rejects_empty_names_and_commas(name):
    # Commas separate characters in exported CSV cells and in CIGA's input,
    # so a name containing one would be split into two characters.
    assert validate_character_name(name)
