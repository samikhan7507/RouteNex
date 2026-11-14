import time, json, base64, hmac, hashlib, secrets
from config import SECRET


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210000)
    return salt + "$" + key.hex()


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
        return hmac.compare_digest(hash_password(password, salt), stored)
    except Exception:
        return False


def otp_hash(phone: str, code: str) -> str:
    """Keyed hash so a leaked DB can't be reversed by brute-forcing 1,000,000 codes."""
    return hmac.new(SECRET.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _b(x):
    return base64.urlsafe_b64encode(x).rstrip(b"=")


def token(data, minutes=60):
    head = _b(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = dict(data, exp=int(time.time()) + minutes * 60)
    payload = _b(json.dumps(body, separators=(",", ":")).encode())
    sig = _b(hmac.new(SECRET.encode(), head + b"." + payload, hashlib.sha256).digest())
    return b".".join([head, payload, sig]).decode()


def decode(value):
    try:
        h, p, s = value.split(".")
        exp = _b(hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(exp, s):
            raise ValueError("signature")
        d = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        if d["exp"] < time.time():
            raise ValueError("expired")
        return d
    except Exception as e:
        raise ValueError("Invalid token") from e


class RateLimiter:
    """Sliding-window limiter (in-memory, per process). Swap for Redis when scaling to many workers."""
    def __init__(self, max_calls: int, window_s: int):
        self.max, self.window, self.hits = max_calls, window_s, {}

    def _recent(self, key):
        now = time.time()
        q = [t for t in self.hits.get(key, []) if now - t < self.window]
        self.hits[key] = q
        return q

    def is_blocked(self, key) -> bool:
        return len(self._recent(key)) >= self.max

    def record(self, key):
        self._recent(key).append(time.time())

    def clear(self, key):
        self.hits.pop(key, None)
