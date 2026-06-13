from api.main import sanitize_name


def test_sanitize_strips_script_content():
    assert "<script>" not in sanitize_name("<script>alert('xss')</script>John")
    assert "alert" not in sanitize_name("<script>alert('xss')</script>John")
    assert sanitize_name("<script>alert('xss')</script>John") == "John"


def test_sanitize_escapes_special_chars():
    assert sanitize_name("Tom & Jerry") == "Tom & Jerry"


def test_sanitize_limits_length():
    assert sanitize_name("A" * 200) == "A" * 100


def test_sanitize_normalizes_whitespace():
    assert sanitize_name("  John   Doe  ") == "John Doe"


def test_sanitize_empty_string():
    assert sanitize_name("") == "Unknown"


def test_sanitize_strips_style_tags():
    assert sanitize_name("<style>body{color:red}</style>Jane") == "Jane"


def test_sanitize_non_string_returns_unknown():
    assert sanitize_name(None) == "Unknown"
