#!/usr/bin/env python3
"""Optional embedded PostgreSQL 16 for LOCAL DEVELOPMENT only.

Install: pip install pgserver==0.1.4
Run in a dedicated terminal: python scripts/dev_db.py --init
Keep that terminal open. Use Docker/managed PostgreSQL in production.
"""
import argparse
from pathlib import Path
import signal
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="Create local role and databases if absent")
    parser.add_argument("--write-env", action="store_true", help="Create .env only if it does not already exist")
    args = parser.parse_args()
    try:
        import pgserver
        import psycopg
    except ImportError:
        raise SystemExit("Local database extras missing: pip install pgserver==0.1.4 psycopg[binary]==3.3.9")
    directory = ROOT / ".local" / "postgres"
    directory.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(directory)
    if args.init:
        with psycopg.connect(server.get_uri(), autocommit=True) as conn:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='routenex'").fetchone():
                conn.execute("CREATE ROLE routenex LOGIN PASSWORD 'routenex'")
            for name in ("routenex", "routenex_test"):
                if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                    conn.execute(f'CREATE DATABASE "{name}" OWNER routenex')
    url = f"postgresql+psycopg://routenex@/routenex?host={directory}"
    test_url = f"postgresql+psycopg://routenex@/routenex_test?host={directory}"
    if args.write_env:
        env = ROOT / ".env"
        if env.exists():
            print("Existing .env left untouched")
        else:
            env.write_text(f"APP_ENV=development\nDATABASE_URL={url}\nTEST_DATABASE_URL={test_url}\nDEMO_MODE=true\nDEMO_AUTOPILOT=true\nSEED_DEMO_DATA=true\nADMIN_EMAIL=samikhan@routenex.in\nADMIN_PASSWORD=Demo@123\nPAYMENT_PROVIDER=demo\nOTP_PROVIDER=console\nLOCATION_PROVIDER=local\n", encoding="utf-8")
            env.chmod(0o600)
    print(f"DATABASE_URL={url}", flush=True)
    print(f"TEST_DATABASE_URL={test_url}", flush=True)
    print("PostgreSQL ready. Keep this process running; Ctrl+C stops it safely.", flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.cleanup()


if __name__ == "__main__":
    main()
