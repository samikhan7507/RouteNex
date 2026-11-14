"""Explicitly restore the public customer demo password; never run automatically."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
import config
from db import init_db, tx
from security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-public-password', action='store_true', help='confirm setting the publicly known password Demo@123')
    args = parser.parse_args()
    if not args.confirm_public_password or not config.DEMO_MODE:
        parser.error('Requires DEMO_MODE=true and --confirm-public-password')
    init_db()
    with tx() as c:
        user = c.execute("SELECT id,active FROM users WHERE email=? AND role='customer'", ('customer@routenex.in',)).fetchone()
        if not user:
            raise SystemExit('Demo customer does not exist; start the app once with DEMO_MODE=true first.')
        if not user['active']:
            raise SystemExit('Demo customer is disabled; reactivate it explicitly in the admin Users screen first.')
        c.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password('Demo@123'), user['id']))
        c.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?, 'PASSWORD_RESET', 'user', ?, ?)",
                  (user['id'], str(user['id']), 'Public demo password restored via CLI'))
    print('Demo customer password restored. This password is public and is only suitable for demos.')


if __name__ == '__main__':
    main()
