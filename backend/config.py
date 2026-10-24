"""Central settings. Reads backend/.env (if present) without overriding real environment variables."""
import os, pathlib

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent


def _load_env(path: pathlib.Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] not in ("'", '"') and " #" in v:
            v = v.split(" #", 1)[0].strip()      # strip trailing inline comment
        os.environ.setdefault(k.strip(), v.strip("\"'"))


_load_env(BASE / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


ENV = os.getenv("ROUTENEX_ENV", "development").lower()
IS_PROD = ENV == "production"
DEMO_MODE = _bool("DEMO_MODE", not IS_PROD)          # enables demo OTP + demo Google profile
DEMO_AUTOPILOT = _bool("DEMO_AUTOPILOT", DEMO_MODE)  # demo drivers drive/accept/finish trips automatically
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()          # auto | ollama | gemini | offline
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")    # Google retires models often; change here if the API says "not found"
ASSISTANT_PER_MIN = int(os.getenv("ASSISTANT_PER_MIN", "20"))
DEMO_PHONE = os.getenv("DEMO_PHONE", "8882846897")
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
OTP_PROVIDER = os.getenv("OTP_PROVIDER", "console")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]

_secret = os.getenv("ROUTENEX_SECRET", "")
if IS_PROD and len(_secret) < 32:
    raise RuntimeError("ROUTENEX_SECRET must be at least 32 characters when ROUTENEX_ENV=production")
SECRET = _secret or "dev-only-insecure-secret-do-not-use-in-production"
INSECURE_SECRET = not _secret

_raw_db = os.getenv("ROUTENEX_DB")
if _raw_db:
    _p = pathlib.Path(_raw_db)
    DB_PATH = (_p if _p.is_absolute() else BASE / _p).resolve()
else:
    DB_PATH = ROOT / "database" / "routenex.db"
