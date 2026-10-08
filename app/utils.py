import re
from urllib.parse import urlparse

import phonenumbers
from werkzeug.security import generate_password_hash, check_password_hash


_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_OTHER_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:(?!\d)", re.I)  # mailto:, javascript: ... (not host:port)
_HOST_RE = re.compile(r"^([a-z0-9-]+\.)+[a-z]{2,}$", re.I)


def normalize_link_url(raw) -> str:
    """Cleans up a web link a person typed. "" stays "" (no link). A link with no
    scheme ("amazon.com/x") gets https:// so it opens the real site instead of
    a path on this one. Raises ValueError for anything that isn't a plain
    http(s) link to a real-looking host."""
    bad = ValueError("Please enter a valid web link, like https://www.example.com/item")
    url = (raw or "").strip()
    if not url:
        return ""
    if len(url) > 500 or re.search(r"\s", url):
        raise bad
    if not _SCHEME_RE.match(url):
        if _OTHER_SCHEME_RE.match(url):
            raise bad
        url = "https://" + url.lstrip("/")
    try:
        parts = urlparse(url)
        parts.port  # raises ValueError on a junk port
        host = (parts.hostname or "").encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        raise bad
    if parts.scheme.lower() not in ("http", "https") or not _HOST_RE.match(host):
        raise bad
    return url


def normalize_username(raw: str) -> str:
    """Lowercases and strips a username; enforces a simple safe charset."""
    username = (raw or "").strip().lower()
    if not re.match(r"^[a-z0-9._-]{3,60}$", username):
        raise ValueError(
            "Username must be 3-60 characters: letters, numbers, dots, "
            "dashes, or underscores only."
        )
    return username


def slugify_username_base(full_name: str) -> str:
    """Best-effort username base from a display name, e.g. "Bob Smith" -> "bobsmith"."""
    base = re.sub(r"[^a-z0-9]", "", (full_name or "").lower())[:40]
    return base or "member"


def hash_password(raw: str) -> str:
    return generate_password_hash(raw)


def verify_password(raw: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, raw)


def normalize_phone(raw: str, region: str = "US") -> str:
    """Normalizes a phone number to E.164 (e.g. "+15551234567").

    `region` is the ISO 3166-1 alpha-2 country the number should be read in
    when it's typed in local/national format (e.g. "555-123-4567" + region
    "US" -> "+15551234567"). If `raw` already starts with "+" it's parsed as
    a full international number and `region` is ignored - so a selected
    country in the UI is just a convenience default, never a restriction:
    typing a full "+44 7911 123456" always works regardless of what's picked.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Please enter a phone number.")
    region = (region or "US").strip().upper() or "US"
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else region)
    except phonenumbers.NumberParseException:
        raise ValueError("Please enter a valid phone number.")
    # is_possible_number (length/shape only), not is_valid_number (real assigned ranges):
    # the latter rejects reserved-for-fictional-use numbers like 555-xxx-xxxx, which this
    # app's own tests and anyone demoing with a placeholder number rely on working.
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("Please enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
