"""Small DB-API bridge for the application's SQLite-style parameterized SQL.

PostgreSQL is used when DATABASE_URL is set. Returned rows support both names
and positions, like sqlite3.Row, and INSERTs into serial-id tables expose lastrowid.
"""
import re
import psycopg2
from psycopg2.extras import DictCursor

ID_TABLES = frozenset('users otp_codes addresses items orders order_items vehicles drivers rides routes alerts maintenance audit_logs notifications payments wallet_txns assistant_actions'.split())


class Result:
    def __init__(self, cursor, lastrowid=None):
        self.cursor, self.lastrowid = cursor, lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class Connection:
    def __init__(self, url):
        self.conn = psycopg2.connect(url, cursor_factory=DictCursor)
        with self.conn.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")

    def execute(self, sql, args=()):
        sql = sql.strip()
        # Only these specific SQLite expressions occur in the application.
        sql = sql.replace("CAST(strftime('%s',created_at) AS INTEGER)", "CAST(EXTRACT(EPOCH FROM created_at::timestamptz) AS BIGINT)")
        sql = sql.replace("strftime('%s','now')", "EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)")
        sql = sql.replace('json_group_array(json_object(', 'json_agg(json_build_object(')
        # Cast JSON aggregates to text: existing clients parse the JSON strings.
        sql = re.sub(r'(json_agg\(json_build_object\([^)]*\)\))', r"COALESCE(\1, '[]'::json)::text", sql)
        ignore = bool(re.match(r'^INSERT OR IGNORE INTO ', sql, re.I))
        sql = re.sub(r'^INSERT OR IGNORE INTO ', 'INSERT INTO ', sql, flags=re.I)
        if re.match(r'^INSERT OR REPLACE INTO meta\b', sql, re.I):
            sql = re.sub(r'^INSERT OR REPLACE', 'INSERT', sql, flags=re.I) + ' ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value'
        elif re.match(r'^INSERT OR REPLACE INTO route_orders\b', sql, re.I):
            sql = re.sub(r'^INSERT OR REPLACE', 'INSERT', sql, flags=re.I) + ' ON CONFLICT (order_id) DO UPDATE SET route_id=EXCLUDED.route_id, stop_sequence=EXCLUDED.stop_sequence, eta=EXCLUDED.eta, arrival_min=EXCLUDED.arrival_min, delay_risk=EXCLUDED.delay_risk'
        elif ignore:
            sql += ' ON CONFLICT DO NOTHING'
        sql = sql.replace('?', '%s')
        match = re.match(r'^INSERT INTO\s+(\w+)', sql, re.I)
        has_id = bool(match and match.group(1).lower() in ID_TABLES)
        if has_id:
            sql += ' RETURNING id'
        cursor = self.conn.cursor()
        cursor.execute(sql, args)
        lastrowid = cursor.fetchone()[0] if has_id and cursor.rowcount else None
        return Result(cursor, lastrowid)

    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()
