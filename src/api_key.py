"""Find the Anthropic API key: environment, then .env, then api_key.txt (never committed)."""
import os
from pathlib import Path

from src.dashboard.auth import ENV_FILE, load_env_file

KEY_NAME = "ANTHROPIC_API_KEY"
KEY_FILE = Path(__file__).resolve().parents[1] / "api_key.txt"


def load_api_key(environ: dict | None = None, env_file: Path = ENV_FILE,
                 key_file: Path = KEY_FILE) -> str | None:
    """Return the key and put it in ANTHROPIC_API_KEY so the client finds it.

    Order: a real environment variable, then .env, then api_key.txt.
    A blank value (like the empty line in .env.example) counts as missing.
    The key is never printed or logged.
    """
    environ = os.environ if environ is None else environ
    if not (environ.get(KEY_NAME) or "").strip():
        environ.pop(KEY_NAME, None)  # a blank value must not block .env
    load_env_file(env_file, environ)
    key = (environ.get(KEY_NAME) or "").strip()
    if not key and key_file.is_file():
        for raw in key_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                key = line
                break
    if key:
        environ[KEY_NAME] = key
        return key
    environ.pop(KEY_NAME, None)
    return None