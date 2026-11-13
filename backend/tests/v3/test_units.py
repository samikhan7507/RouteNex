import hashlib
import hmac
import importlib.util
import pathlib

import pytest
from fastapi import HTTPException

from app.core.security import hash_password, protect_code, reveal_code, verify_password
from app.services import pricing
from app.services.common import paise
from app.services.geo import haversine_km

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_paise_strict_two_decimals():
    assert paise("89.00") == 8900
    assert paise(0.1) == 10
    with pytest.raises(HTTPException):
        paise("10.005")
    with pytest.raises(HTTPException):
        paise("-1")


def test_money_migration_rounds_half_up():
    spec = importlib.util.spec_from_file_location("migrate_sqlite", ROOT / "scripts" / "migrate_sqlite.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.paise(89.999) == 9000
    assert mod.paise(-80.1) == -8010
    assert mod.parse_ts(1700000000).tzinfo is not None
    assert mod.parse_ts("2026-11-10 10:00:00").tzinfo is not None


def test_quote_signature_roundtrip_tamper_and_expiry(monkeypatch):
    data = {"kind": "ride", "quotes": [{"vehicle_class": "bike", "fare_paise": 5000}]}
    token = pricing.issue_quote(7, data)
    assert pricing.read_quote(token, 7)["kind"] == "ride"
    with pytest.raises(HTTPException):
        pricing.read_quote(token, 8)
    raw, sig = token.split(".")
    with pytest.raises(HTTPException):
        pricing.read_quote(raw + "." + "0" * 64, 7)
    monkeypatch.setattr(pricing.time, "time", lambda: pricing.time.time() + 400)
    with pytest.raises(HTTPException):
        pricing.read_quote(token, 7)


def test_password_hashing_and_legacy_upgrade():
    encoded = hash_password("CorrectHorse@123")
    assert encoded.startswith("$argon2")
    assert verify_password("CorrectHorse@123", encoded)
    assert not verify_password("wrong", encoded)
    salt = "legacy-salt"
    legacy = salt + "$" + hashlib.pbkdf2_hmac("sha256", b"OldPassword@123", salt.encode(), 210000).hex()
    assert verify_password("OldPassword@123", legacy)
    assert not verify_password("nope", legacy)


def test_proof_codes_encrypted_at_rest():
    code = "123456"
    encrypted = protect_code(code)
    assert encrypted != code
    assert reveal_code(encrypted) == code
    assert reveal_code(None) is None


def test_haversine_jaipur_landmarks():
    km = haversine_km(26.8540, 75.8243, 26.9126, 75.7442)
    assert 8 < km < 12


def test_hmac_constant_time_comparison():
    assert hmac.compare_digest("abc", "abc")
    assert not hmac.compare_digest("abc", "abd")
