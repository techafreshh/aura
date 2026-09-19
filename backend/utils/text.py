"""Free-text sanitizers shared by the API routers.

Lives here (not in api.main) so routers that main.py mounts can import them
without a circular import; api.main re-exports the names for backwards
compatibility with existing imports/tests.
"""

import re


def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "Unknown"


def sanitize_text(text: str, max_length: int) -> str:
    """Strip HTML tags and cap length for free-text inputs (job descriptions, etc.)."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_length]


def sanitize_rich_text(text: str, max_length: int) -> str:
    """Like sanitize_text, but also drops the *content* of active tags.

    Profile fields are stored verbatim and re-rendered in dashboards, so a
    pasted ``<script>…</script>`` must not leave its payload behind as text
    the way plain tag-stripping would.
    """
    if not isinstance(text, str):
        return ""
    text = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_length]
