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
