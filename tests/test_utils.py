import pytest

from app.utils import normalize_phone, normalize_username


@pytest.mark.parametrize("raw", [
    "5551234567",
    "(555) 123-4567",
    "555-123-4567",
    "1-555-123-4567",
    "15551234567",
])
def test_normalize_phone_accepts_common_us_formats(raw):
    assert normalize_phone(raw) == "+15551234567"
    assert normalize_phone(raw, "US") == "+15551234567"


@pytest.mark.parametrize("raw", ["", "12345", "555-123-45678", "not a phone"])
def test_normalize_phone_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


@pytest.mark.parametrize("raw,region,expected", [
    ("9171234567", "PH", "+639171234567"),       # national format, region picks the country
    ("+639171234567", "US", "+639171234567"),    # a leading "+" always wins over the region
    ("7911123456", "GB", "+447911123456"),
    ("91 98765 43210", "IN", "+919876543210"),
])
def test_normalize_phone_honors_region_and_leading_plus(raw, region, expected):
    assert normalize_phone(raw, region) == expected


def test_normalize_phone_defaults_to_us_when_no_region_given():
    assert normalize_phone("5551234567") == normalize_phone("5551234567", "US")


@pytest.mark.parametrize("raw,expected", [
    ("LolaNena", "lolanena"),
    ("  tito_ben  ", "tito_ben"),
    ("a.b-c_123", "a.b-c_123"),
])
def test_normalize_username_accepts_valid(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("raw", ["", "ab", "has space", "has@symbol", "x" * 61])
def test_normalize_username_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_username(raw)


from app.utils import (normalize_link_url, normalize_email, clean_text, parse_bool, parse_id,
                       parse_colors, parse_amount, InputError)


@pytest.mark.parametrize("raw,expected", [
    ("amazon.com/x", "https://amazon.com/x"),
    ("www.target.com:8080/p", "https://www.target.com:8080/p"),
    ("https://www.etsy.com/listing/1?a=b#c", "https://www.etsy.com/listing/1?a=b#c"),
    ("http://amzn.to/3xYz", "http://amzn.to/3xYz"),
    ("  //example.co.uk/item  ", "https://example.co.uk/item"),
    ("", ""),
])
def test_link_urls_accepted(raw, expected):
    assert normalize_link_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "sweater", "red sweater size M", "javascript:alert(1)", "mailto:a@b.com", "ftp://x.com",
    "data:text/html,hi", "https://user:pw@evil.com", "https://evil.com@good.com", "http://localhost:5000",
    "http://192.168.1.1/x", "https://-bad.com", "https://a..com", "https://exa mple.com",
    "https://ex.com/<script>", 'https://ex.com/"x', "https://ex.com/a\b", "https://ex.com:99999",
    "https://ex.com/\nx", "https://" + "a" * 500 + ".com", ["https://ex.com"], 5,
])
def test_link_urls_rejected(raw):
    with pytest.raises(InputError):
        normalize_link_url(raw)


@pytest.mark.parametrize("raw,expected", [("Ana@Example.COM ", "ana@example.com"), ("", ""), (None, "")])
def test_email_accepted(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["ana", "ana@", "@x.com", "ana@x", "a b@x.com", "ana@x.c", ["a@x.com"]])
def test_email_rejected(raw):
    with pytest.raises(InputError):
        normalize_email(raw)


def test_clean_text_trims_strips_control_chars_and_checks_length():
    assert clean_text("  hi\x00 there\x07 ", 20, "Name") == "hi there"
    assert clean_text("a\nb", 20, "Name") == "a b"                        # single-line fields
    assert clean_text("a\r\nb", 20, "Note", multiline=True) == "a\nb"     # multiline keeps breaks
    assert clean_text(None, 5, "Name") == "" and clean_text(42, 5, "Name") == "42"
    with pytest.raises(InputError, match="at most 5"):
        clean_text("toolong", 5, "Name")
    with pytest.raises(InputError, match="has to be text"):
        clean_text({"a": 1}, 5, "Name")
    with pytest.raises(InputError, match="Please fill in name"):
        clean_text("   ", 5, "Name", required=True)


def test_parse_bool_parse_id_parse_amount():
    assert [parse_bool(v) for v in (True, "true", "on", 1, False, "false", "0", 0, None, "")] == \
        [True] * 4 + [False] * 6
    for bad in ("maybe", 2, [True]):
        with pytest.raises(InputError):
            parse_bool(bad)
    assert (parse_id("7"), parse_id(7), parse_id(None), parse_id("")) == (7, 7, None, None)
    for bad in ("x", -1, 0, True, 1.5, [1], "1e3"):
        with pytest.raises(InputError):
            parse_id(bad)
    assert str(parse_amount("25.5")) == "25.50" and parse_amount("") is None
    for bad in ("lots", -5, "NaN", "Infinity", True, [1], "1e12"):
        with pytest.raises(InputError):
            parse_amount(bad)


def test_parse_colors():
    assert parse_colors(["#AABBCC", "#aabbcc", "#000000"]) == ["#aabbcc", "#000000"]
    assert parse_colors(None) == [] and parse_colors([]) == []
    for bad in ("#aabbcc", ["teal"], ["#abc"], [None], ["#aabbcc\""]):
        with pytest.raises(InputError):
            parse_colors(bad)


def test_old_color_names_carry_over_to_picked_colors():
    import importlib.util, pathlib
    path = next(pathlib.Path("migrations/versions").glob("c7f1e9a2d405_*.py"))
    spec = importlib.util.spec_from_file_location("mig", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig._to_colors("Teal") == "#008080"
    assert mig._to_colors("Sage green, navy and Gold") == "#9caf88,#000080,#ffd700"
    assert mig._to_colors("sparkly unicorn") is None
