import pytest

from app.utils import normalize_us_phone


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
