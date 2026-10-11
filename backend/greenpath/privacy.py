import re


_PHONE_NUMBER = re.compile(r"(?<!\d)\+?(?:\d[\s().\-–—]*){8,15}(?!\d)")
_EMAIL = re.compile(
    r"\b[a-z0-9._%+-]+\s*(?:@|\[at\]|\(at\)|\bat\b)\s*"
    r"[a-z0-9.-]+\s*(?:\.|\[dot\]|\(dot\)|\bdot\b)\s*[a-z]{2,}\b",
    re.IGNORECASE,
)
_COORDINATES = re.compile(
    r"(?<!\w)[+-]?\d{1,2}\.\d{3,}\s*[,;/ ]\s*[+-]?\d{1,3}\.\d{3,}(?!\w)"
)
_EXACT_ADDRESS = re.compile(
    r"\b(?:house\s*(?:no\.?|number|#)|kebele|street|st\.|road|rd\.|"
    r"building|block|gps|coordinates?|map\s*pin)\s*[:#-]?\s*"
    r"[\w.+/-]{1,}\b",
    re.IGNORECASE,
)
_EXTERNAL_SERVICE = re.compile(
    r"\b(?:whats?[\s._-]*app|telegram|signal|viber|imo|wechat|"
    r"instagram|facebook|messenger)\b",
    re.IGNORECASE,
)
_EXTERNAL_CONTACT_INSTRUCTION = re.compile(
    r"\b(?:call|text|contact|message|reach|write)\s+(?:me|us)\b"
    r".{0,35}\b(?:outside|off[\s-]?platform|on|via|through|at)\b",
    re.IGNORECASE,
)
_HANDLE = re.compile(r"(?<![\w@])@[a-z0-9_.]{3,}", re.IGNORECASE)
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)


def contains_restricted_content(text):
    """Detect contact details and precise locations before content is stored."""
    if not text:
        return False
    return any(
        pattern.search(text)
        for pattern in (
            _PHONE_NUMBER,
            _EMAIL,
            _COORDINATES,
            _EXACT_ADDRESS,
            _EXTERNAL_SERVICE,
            _EXTERNAL_CONTACT_INSTRUCTION,
            _HANDLE,
            _URL,
        )
    )


def restricted_content_message():
    return (
        "This message may contain private contact details or a precise location. "
        "Please remove them and continue your discussion here."
    )
