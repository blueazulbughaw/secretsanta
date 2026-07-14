import pytest

from app.utils import normalize_us_phone, normalize_username


@pytest.mark.parametrize("raw", [
    "5551234567",
    "(555) 123-4567",
    "555-123-4567",
    "1-555-123-4567",
    "15551234567",
])
def test_normalize_us_phone_accepts_common_formats(raw):
    assert normalize_us_phone(raw) == "+15551234567"


@pytest.mark.parametrize("raw", ["", "12345", "555-123-45678", "not a phone"])
def test_normalize_us_phone_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_us_phone(raw)


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
