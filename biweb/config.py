import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = Path(os.environ.get("BIWEB_VAR", str(BASE_DIR / "var")))
METADATA_DB = VAR_DIR / "biweb.db"
SAMPLE_DB = VAR_DIR / "sample.db"
IMPORTED_DB = VAR_DIR / "imported.db"

DESIGN_ENABLED = os.environ.get("BIWEB_DESIGN", "1").lower() not in {"0", "false", "no", "off"}
DESIGN_TOKEN = os.environ.get("BIWEB_DESIGN_TOKEN", "")
MAX_QUERY_ROWS = int(os.environ.get("BIWEB_MAX_ROWS", "20000"))
QUERY_TIMEOUT_MS = int(os.environ.get("BIWEB_QUERY_TIMEOUT_MS", "8000"))
IMPORT_MAX_ROWS = int(os.environ.get("BIWEB_IMPORT_MAX_ROWS", "200000"))
API_SCRIPT_TIMEOUT = int(os.environ.get("BIWEB_API_TIMEOUT", "30"))
MAX_UPLOAD_BYTES = int(os.environ.get("BIWEB_MAX_UPLOAD_MB", "64")) * 1024 * 1024
SQLITE_ROOTS = [
    Path(item).expanduser().resolve()
    for item in os.environ.get("BIWEB_SQLITE_ROOTS", "").split(os.pathsep)
    if item.strip()
]

DEMO_USERS = os.environ.get("BIWEB_DEMO_USERS", "1").lower() not in {"0", "false", "no", "off"}
ADMIN_PASSWORD = os.environ.get("BIWEB_ADMIN_PASSWORD", "admin123")
SESSION_COOKIE_SECURE = os.environ.get("BIWEB_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}
PASSWORD_MIN_LENGTH = 8


def ensure_dirs() -> None:
    VAR_DIR.mkdir(parents=True, exist_ok=True)


def _secret_key() -> str:
    env = os.environ.get("BIWEB_SECRET_KEY")
    if env:
        return env
    ensure_dirs()
    path = VAR_DIR / "secret.key"
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_hex(32)
        path.write_text(value, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value
    except OSError:
        return secrets.token_hex(32)


SECRET_KEY = _secret_key()
