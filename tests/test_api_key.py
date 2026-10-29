from src.api_key import load_api_key

KEY = "ANTHROPIC_API_KEY"


def test_environment_variable_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-env-file\n", encoding="utf-8")
    key_file = tmp_path / "api_key.txt"
    key_file.write_text("from-key-file\n", encoding="utf-8")
    environ = {KEY: "from-environment"}
    assert load_api_key(environ, env_file, key_file) == "from-environment"


def test_env_file_is_used_when_the_variable_is_missing_or_blank(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-env-file\n", encoding="utf-8")
    for environ in ({}, {KEY: ""}):
        assert load_api_key(environ, env_file, tmp_path / "api_key.txt") == "from-env-file"
        assert environ[KEY] == "from-env-file"


def test_key_file_is_the_last_resort(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")
    key_file = tmp_path / "api_key.txt"
    key_file.write_text("# comment\n\nfrom-key-file\n", encoding="utf-8")
    environ = {}
    assert load_api_key(environ, env_file, key_file) == "from-key-file"
    assert environ[KEY] == "from-key-file"


def test_no_key_anywhere_returns_none(tmp_path):
    environ = {}
    assert load_api_key(environ, tmp_path / ".env", tmp_path / "api_key.txt") is None
    assert KEY not in environ