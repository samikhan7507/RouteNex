"""Copy an existing SQLite database into a *new, empty* PostgreSQL database.

Stop all app writers and back up the SQLite file before running. DATABASE_URL
must point at the destination, not at a live database. Nothing is deleted from
SQLite; destination data and foreign keys are copied in one transaction.
"""
import argparse
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'backend'))
import config
import db
from psycopg2 import sql
from psycopg2.extras import execute_values

TABLES = ['users', 'otp_codes', 'addresses', 'items', 'vehicles', 'drivers', 'rides', 'routes', 'orders',
          'route_orders', 'order_items', 'alerts', 'maintenance', 'audit_logs', 'notifications', 'meta',
          'parcels', 'payments', 'wallet_txns', 'coupons', 'coupon_uses', 'assistant_actions']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_file', type=pathlib.Path)
    args = parser.parse_args()
    if not config.DATABASE_URL:
        parser.error('Set DATABASE_URL to the empty PostgreSQL destination')
    source_path = args.sqlite_file.resolve()
    if not source_path.is_file():
        parser.error('SQLite source file does not exist')
    source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)
    source_tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'users' not in source_tables:
        parser.error('Source does not look like a RouteNex database')
    db.init_db()
    try:
        with db.tx() as wrapper:
            cur = wrapper.conn.cursor()
            # Reject a destination containing application data; the only permitted
            # rows are default coupons inserted by init_db itself.
            cur.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(sql.SQL(', ').join(map(sql.Identifier, TABLES))))
            for table in TABLES:
                if table != 'coupons':
                    cur.execute(sql.SQL('SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)').format(sql.Identifier(table)))
                    if cur.fetchone()[0]:
                        raise RuntimeError(f'Destination is not empty ({table}); refusing to overwrite data')
            cur.execute('SELECT code,title,scope,kind,value,max_discount,min_amount,one_time FROM coupons ORDER BY code')
            existing_coupons = [tuple(row) for row in cur.fetchall()]
            if existing_coupons != sorted(db.DEFAULT_COUPONS):
                raise RuntimeError('Destination coupons were modified; refusing to overwrite data')
            if 'coupons' in source_tables:
                cur.execute('DELETE FROM coupons')
            for table in TABLES:
                if table not in source_tables:
                    continue
                source_cols = [r[1] for r in source.execute(f'PRAGMA table_info("{table}")')]
                cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s', (table,))
                target_cols = {r[0] for r in cur.fetchall()}
                columns = [name for name in source_cols if name in target_cols]
                if not columns:
                    continue
                names = ','.join('"' + n.replace('"', '""') + '"' for n in columns)
                records = source.execute(f'SELECT {names} FROM "{table}"')
                insert = sql.SQL('INSERT INTO {} ({}) VALUES %s').format(sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)))
                count = 0
                while batch := records.fetchmany(500):
                    execute_values(cur, insert.as_string(wrapper.conn), batch)
                    count += len(batch)
                if 'id' in columns:
                    cur.execute('SELECT pg_get_serial_sequence(%s, %s)', (table, 'id'))
                    sequence = cur.fetchone()[0]
                    if sequence:
                        cur.execute(sql.SQL('SELECT setval(%s, GREATEST(COALESCE(MAX(id), 0), 1), MAX(id) IS NOT NULL) FROM {}').format(sql.Identifier(table)), (sequence,))
                print(f'{table}: {count} rows copied')
        print('Migration committed. Start the app only after checking the copied data.')
    finally:
        source.close()


if __name__ == '__main__':
    main()
