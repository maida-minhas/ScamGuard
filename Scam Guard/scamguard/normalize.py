import hashlib
from urllib.parse import parse_qs, urlsplit

from scamguard.models import EntityType

_PHONE_ALLOWED_CHARS = set("0123456789+ ()-.")
_MIN_PHONE_DIGITS = 7


def detect_type(raw: str) -> EntityType | None:
    """Classify raw search input as PHONE, INSTAGRAM, FACEBOOK, or None."""
    text = (raw or "").strip()
    if not text:
        return None

    if set(text) <= _PHONE_ALLOWED_CHARS:
        digits = sum(ch.isdigit() for ch in text)
        if digits >= _MIN_PHONE_DIGITS:
            return EntityType.PHONE

    lowered = text.lower()
    if "instagram.com" in lowered or text.startswith("@"):
        return EntityType.INSTAGRAM
    if "facebook.com" in lowered:
        return EntityType.FACEBOOK
    return None


def normalize(raw: str, entity_type: EntityType) -> str:
    """Return the canonical identifier for the given input and type."""
    text = raw.strip()
    if entity_type == EntityType.PHONE:
        return _normalize_phone(text)
    if entity_type == EntityType.INSTAGRAM:
        return _normalize_instagram(text)
    if entity_type == EntityType.FACEBOOK:
        return _normalize_facebook(text)
    raise ValueError(f"Unknown entity type: {entity_type!r}")


def mask(canonical: str, entity_type: EntityType) -> str:
    """Return the masked display form of a canonical identifier."""
    if entity_type == EntityType.PHONE:
        return _mask_phone(canonical)
    if entity_type == EntityType.INSTAGRAM:
        return _mask_instagram(canonical)
    if entity_type == EntityType.FACEBOOK:
        return canonical[:20] + "…"
    raise ValueError(f"Unknown entity type: {entity_type!r}")


def identifier_hash(canonical: str) -> str:
    """Return the SHA-256 hex digest of the canonical identifier."""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_phone(text: str) -> str:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError("Phone input contains no digits")
    if digits.startswith("0092"):
        digits = "0" + digits[4:]
    elif digits.startswith("92"):
        digits = "0" + digits[2:]
    if not digits.startswith("0"):
        digits = "0" + digits
    return digits


def _normalize_instagram(text: str) -> str:
    if "instagram.com" in text.lower():
        url = text if "://" in text else f"https://{text}"
        path = urlsplit(url).path.strip("/")
        handle = path.split("/")[0] if path else ""
    elif text.startswith("@"):
        handle = text[1:]
    else:
        handle = text
    if not handle:
        raise ValueError("Instagram input has no handle")
    return handle.lower()


def _normalize_facebook(text: str) -> str:
    url = text if "://" in text else f"https://{text}"
    parts = urlsplit(url)
    if not parts.netloc:
        raise ValueError("Facebook input is not a URL")
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/").lower()
    canonical = host + path
    if path.endswith("profile.php"):
        id_value = parse_qs(parts.query).get("id", [None])[0]
        if id_value is not None:
            canonical += f"?id={id_value}"
    return canonical


def _mask_phone(canonical: str) -> str:
    if len(canonical) < 8:
        return "*" * len(canonical)
    head, middle, tail = canonical[:2], canonical[2:-4], canonical[-4:]
    masked_middle = "**"
    if len(middle) > 2:
        masked_middle += "-" + "*" * (len(middle) - 2)
    return f"{head}{masked_middle}-{tail}"


def _mask_instagram(canonical: str) -> str:
    dot = canonical.rfind(".")
    if dot > 1:
        middle, tail = canonical[2:dot], canonical[dot:]
    else:
        middle, tail = canonical[2:-2], canonical[-2:]
    stars = "*" * len(middle) if middle else "****"
    return f"@{canonical[:2]}{stars}{tail}"
