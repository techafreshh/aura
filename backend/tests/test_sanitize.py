from api.main import sanitize_name

def test_sanitize_strips_html_tags():
    assert sanitize_name("<script>alert('xss')</script>John") == "alert(&#x27;xss&#x27;)John"

def test_sanitize_escapes_special_chars():
    assert sanitize_name("Tom & Jerry") == "Tom &amp; Jerry"

def test_sanitize_limits_length():
    assert sanitize_name("A" * 200) == "A" * 100

def test_sanitize_normalizes_whitespace():
    assert sanitize_name("  John   Doe  ") == "John Doe"

def test_sanitize_empty_string():
    assert sanitize_name("") == ""
