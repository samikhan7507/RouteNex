"""Reserved RouteNex demo identities.

These credentials are intentionally public for local/demo deployments only.
Production/staging refuse demo mode, and bootstrap refuses to seed them there.
"""
from __future__ import annotations

DEMO_PASSWORD = "Demo@123"
DEMO_ADMIN_EMAIL = "samikhan@routenex.in"

DEMO_ACCOUNTS: list[dict[str, str | None]] = [
    {"label": "Admin", "role": "admin", "email": DEMO_ADMIN_EMAIL, "name": "Sami Khan", "phone": None},
    {"label": "Customer", "role": "customer", "email": "customer@routenex.in", "name": "Aarav Sharma", "phone": "+919876543210"},
    {"label": "Driver", "role": "driver", "email": "driver@routenex.in", "name": "Diya Rathore", "phone": "+919000000002"},
    {"label": "Dispatcher", "role": "dispatcher", "email": "dispatcher@routenex.in", "name": "Kabir Mehta", "phone": "+919000000003"},
    {"label": "Fleet manager", "role": "fleet_manager", "email": "fleet@routenex.in", "name": "Meera Joshi", "phone": "+919000000004"},
]


def public_demo_accounts() -> list[dict[str, str]]:
    """Login-panel metadata; never includes password hashes or private user rows."""
    return [{"label": str(a["label"]), "role": str(a["role"]), "email": str(a["email"])} for a in DEMO_ACCOUNTS]
