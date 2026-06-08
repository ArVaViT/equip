"""Guards the CSV formula-injection neutralizer on the grade export."""

from app.api.v1.grades import _csv_safe


def test_csv_safe_prefixes_formula_leading_chars() -> None:
    for trigger in ("=", "+", "-", "@", "\t", "\r"):
        payload = f'{trigger}HYPERLINK("http://evil","x")'
        assert _csv_safe(payload) == "'" + payload


def test_csv_safe_passes_plain_values_through() -> None:
    assert _csv_safe("Vadym Arnaut") == "Vadym Arnaut"
    assert _csv_safe("") == ""
    assert _csv_safe("a=b+c") == "a=b+c"  # trigger char not in leading position
    assert _csv_safe(42) == 42
    assert _csv_safe(None) is None
