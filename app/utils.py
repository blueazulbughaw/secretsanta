import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import phonenumbers
from werkzeug.security import generate_password_hash, check_password_hash


class InputError(ValueError):
    """Bad input from the person using the app; the message is shown to them as-is.
    Raised anywhere while handling an /api request, it becomes a 400 (see create_app)."""


_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_OTHER_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:(?!\d)", re.I)  # mailto:, javascript: ... (not host:port)
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST_RE = re.compile(rf"^(?:{_LABEL}\.)+(?:[a-z]{{2,63}}|xn--[a-z0-9-]{{1,59}})$", re.I)
_URL_BAD_CHARS = re.compile(r"[\s<>\"'`\\{}|^\x00-\x1f\x7f]")
LINK_HELP = "Please enter a valid web link, like https://www.example.com/item"


def normalize_link_url(raw) -> str:
    """Cleans up a web link a person typed. "" stays "" (no link). A link with no
    scheme ("amazon.com/x") gets https:// so it opens the real site instead of
    a path on this one. Raises InputError for anything that isn't a plain
    http(s) link to a real-looking public host name: no other schemes, no
    user:password@, no bare words, IP addresses or localhost, no spaces or
    characters that don't belong in a link. Mirrored by normalizeUrl() in app.js."""
    bad = InputError(LINK_HELP)
    if raw is not None and not isinstance(raw, str):
        raise bad
    url = (raw or "").strip()
    if not url:
        return ""
    if len(url) > 500 or _URL_BAD_CHARS.search(url):
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
    if (parts.scheme.lower() not in ("http", "https") or "@" in parts.netloc
            or len(host) > 253 or not _HOST_RE.match(host)):
        raise bad
    return url


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(raw, limit, label, *, required=False, multiline=False):
    """A free-text field: must be text (or missing), is trimmed, has control
    characters removed (and, unless `multiline`, line breaks turned into spaces),
    and may be at most `limit` characters. Returns "" when blank (or raises
    InputError if `required`). `label` names the field in messages."""
    if raw is None:
        raw = ""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = str(raw)
    if not isinstance(raw, str):
        raise InputError(f"{label} has to be text.")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        text = re.sub(r"[\n\t]+", " ", text)
    text = _CONTROL_CHARS.sub("", text).strip()
    if required and not text:
        raise InputError(f"Please fill in {label[0].lower() + label[1:]}.")
    if len(text) > limit:
        raise InputError(f"{label} can be at most {limit} characters.")
    return text


_EMAIL_RE = re.compile(r"^[^@\s]+@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


def normalize_email(raw) -> str:
    """"" for no email, else a lowercased, plausible address. Raises InputError."""
    email = clean_text(raw, 255, "Email").lower()
    if email and not _EMAIL_RE.match(email):
        raise InputError("Please enter a valid email address, like name@example.com.")
    return email


def parse_bool(raw, label="That setting") -> bool:
    """A yes/no setting sent as JSON or a form value. Rejects anything ambiguous
    (bool("false") would otherwise be True)."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str) and raw.strip().lower() in ("true", "1", "on", "yes", "false", "0", "off", "no", ""):
        return raw.strip().lower() in ("true", "1", "on", "yes")
    raise InputError(f"{label} has to be on or off.")


def parse_id(raw, label="That choice"):
    """An optional record id: None/"" -> None, else a positive int. Raises InputError."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise InputError(f"{label} isn't valid.")
    text = str(raw).strip()
    if not text.isdigit() or int(text) < 1:
        raise InputError(f"{label} isn't valid.")
    return int(text)


MAX_FAVORITE_COLORS = 8
_HEX_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")


def parse_colors(raw):
    """A list of "#rrggbb" colors (from the color picker): lowercased, duplicates
    dropped, at most MAX_FAVORITE_COLORS. Raises InputError."""
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        raise InputError("Favorite colors have to be a list of colors.")
    colors = []
    for c in raw:
        c = c.strip().lower() if isinstance(c, str) else ""
        if not _HEX_COLOR_RE.match(c):
            raise InputError("Please pick your favorite colors with the color picker.")
        if c not in colors:
            colors.append(c)
    if len(colors) > MAX_FAVORITE_COLORS:
        raise InputError(f"You can pick up to {MAX_FAVORITE_COLORS} favorite colors.")
    return colors


def parse_amount(raw, what="amount"):
    """A money amount from a form: blank -> None, else a non-negative Decimal with
    two places. Raises InputError with a plain-language message."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    bad = InputError(f"Please enter the {what} as a number, like 25 or 25.50.")
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise bad
    try:
        amount = Decimal(str(raw).strip())
    except InvalidOperation:
        raise bad
    if not amount.is_finite() or amount < 0 or amount >= Decimal("100000000"):
        raise bad
    return amount.quantize(Decimal("0.01"))


def normalize_username(raw: str) -> str:
    """Lowercases and strips a username; enforces a simple safe charset."""
    username = (raw if isinstance(raw, str) else "").strip().lower()
    if not re.match(r"^[a-z0-9._-]{3,60}$", username):
        raise InputError(
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


PASSWORD_MIN, PASSWORD_MAX = 8, 128


def check_new_password(raw) -> str:
    if not isinstance(raw, str) or len(raw) < PASSWORD_MIN:
        raise InputError(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(raw) > PASSWORD_MAX:
        raise InputError(f"Password can be at most {PASSWORD_MAX} characters.")
    return raw


def verify_password(raw: str, password_hash: str) -> bool:
    if not password_hash or not isinstance(raw, str) or len(raw) > PASSWORD_MAX:
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
    raw = (raw if isinstance(raw, str) else "").strip()
    if not raw:
        raise InputError("Please enter a phone number.")
    region = (region if isinstance(region, str) else "US").strip().upper() or "US"
    if len(raw) > 30:
        raise InputError("Please enter a valid phone number.")
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else region)
    except phonenumbers.NumberParseException:
        raise InputError("Please enter a valid phone number.")
    # is_possible_number (length/shape only), not is_valid_number (real assigned ranges):
    # the latter rejects reserved-for-fictional-use numbers like 555-xxx-xxxx, which this
    # app's own tests and anyone demoing with a placeholder number rely on working.
    if not phonenumbers.is_possible_number(parsed):
        raise InputError("Please enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def json_body() -> dict:
    """The request's JSON object, or {} when there's no JSON body. Anything else
    (a list, a bare string...) is an InputError rather than a crash further on."""
    from flask import request
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise InputError("Something was wrong with that request. Please refresh and try again.")
    return data
