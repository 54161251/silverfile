"""Staff sign-in for the dashboard (B7, R6, R16).

src/human.py requires the dashboard to authenticate staff before it exposes resolution
controls. Allowed staff IDs and one shared passcode come from the environment or a local
.env file, never from code. If either is missing, sign-in is refused (fail closed) and the
dashboard stays read-only. The signed-in staff ID becomes `resolved_by` on every resolution.

Variables (add them to .env; .env.example lists them with synthetic demo values):
    SILVERFILE_STAFF_IDS        comma-separated staff IDs, e.g. "staff_jlee,demo_staff"
    SILVERFILE_STAFF_PASSCODE   shared passcode for this synthetic demo deployment
"""
from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

STAFF_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class Staff:
    staff_id: str


def load_env_file(path: Path = ENV_FILE, environ: dict | None = None) -> None:
    """Copy KEY=VALUE lines from .env into the environment without overriding real variables.

    A small parser instead of a new dependency (R5). Comments and blank lines are skipped.
    """
    environ = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        environ.setdefault(key, value.strip().strip('"').strip("'"))


def allowed_staff(env: Mapping[str, str] | None = None) -> set[str]:
    env = os.environ if env is None else env
    ids = {part.strip() for part in env.get("SILVERFILE_STAFF_IDS", "").split(",")}
    return {staff_id for staff_id in ids if STAFF_ID_PATTERN.fullmatch(staff_id)}


def sign_in_available(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(allowed_staff(env)) and bool(env.get("SILVERFILE_STAFF_PASSCODE", ""))


def authenticate(staff_id: str, passcode: str, env: Mapping[str, str] | None = None) -> Staff | None:
    """Return the staff identity, or None. Never says which of the two fields was wrong."""
    env = os.environ if env is None else env
    secret = env.get("SILVERFILE_STAFF_PASSCODE", "")
    staff_id = (staff_id or "").strip().lower()
    if not sign_in_available(env):
        return None
    # Compare the passcode even for an unknown ID so both failures take similar time.
    passcode_ok = hmac.compare_digest((passcode or "").encode("utf-8"), secret.encode("utf-8"))
    if passcode_ok and staff_id in allowed_staff(env):
        return Staff(staff_id)
    return None
