from src.workflows.configure import _clean_env


def test_clean_env_strips_trailing_comment_on_blank_value():
    # Regression: dotenv doesn't always strip "# comment" when the value itself is blank,
    # leaving the literal comment text in os.environ instead of an empty string.
    assert _clean_env("          # 0-100") == ""


def test_clean_env_strips_trailing_comment_on_real_value():
    assert _clean_env("40          # 0-100") == "40"


def test_clean_env_passes_through_plain_value():
    assert _clean_env("40") == "40"


def test_clean_env_passes_through_empty_string():
    assert _clean_env("") == ""
