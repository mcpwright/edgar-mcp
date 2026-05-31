from edgar_mcp.xmlutil import clean, to_bool, to_float, to_int


def test_clean() -> None:
    assert clean("  hi ") == "hi"
    assert clean("") is None
    assert clean("   ") is None
    assert clean(None) is None


def test_to_int() -> None:
    assert to_int("3650000") == 3_650_000
    assert to_int("1,450,000") == 1_450_000
    assert to_int("-5") == -5
    assert to_int("Indefinite") is None
    assert to_int(None) is None


def test_to_float() -> None:
    assert to_float("140.00000") == 140.0
    assert to_float("-3000.00") == -3000.0
    assert to_float("n/a") is None
    assert to_float(None) is None


def test_to_bool_handles_both_styles() -> None:
    # Form D uses true/false; Form C uses Y/N — one helper covers both.
    assert to_bool("true") is True
    assert to_bool("false") is False
    assert to_bool("Y") is True
    assert to_bool("N") is False
    assert to_bool("maybe") is None
    assert to_bool(None) is None
