"""Optional real-PostgreSQL integration; set TEST_DATABASE_URL to a disposable test server."""
import os
import pathlib
import subprocess
import sys
import uuid
import pytest


def test_postgres_end_to_end():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to run PostgreSQL integration')
    import psycopg2
    from psycopg2 import sql
    from urllib.parse import quote
    schema = 'test_' + uuid.uuid4().hex
    root = pathlib.Path(__file__).resolve().parents[2]
    connection = psycopg2.connect(url)
    connection.autocommit = True
    with connection.cursor() as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        separator = '&' if '?' in url else '?'
        env = dict(os.environ, DATABASE_URL=url + separator + 'options=' + quote('-csearch_path=' + schema),
                   PYTHONPATH=str(root / 'backend'), ROUTENEX_ENV='development', DEMO_MODE='true',
                   DEMO_AUTOPILOT='true', ROUTENEX_OFFLINE='1', ROUTENEX_ML_AUTOTRAIN='0',
                   LLM_PROVIDER='offline', ADMIN_EMAIL='admin@test.in', ADMIN_PASSWORD='owner-pass-123')
        subprocess.run([sys.executable, str(root / 'backend/tests/pg_scenario.py')], env=env, cwd=root, check=True)
    finally:
        with connection.cursor() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        connection.close()


def test_sqlite_import_is_atomic_and_refuses_nonempty_destination(tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to run PostgreSQL integration')
    import psycopg2
    import sqlite3
    from psycopg2 import sql
    from urllib.parse import quote
    schema = 'test_' + uuid.uuid4().hex
    root = pathlib.Path(__file__).resolve().parents[2]
    source = tmp_path / 'source.db'
    conn = sqlite3.connect(source)
    conn.executescript((root / 'database/schema.sql').read_text())
    conn.execute("INSERT INTO users(id,name,email,role) VALUES(42,'Imported','imported@test.in','customer')")
    conn.execute("INSERT INTO addresses(id,user_id,label) VALUES(7,42,'Home')")
    conn.commit(); conn.close()
    pg = psycopg2.connect(url); pg.autocommit = True
    with pg.cursor() as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        separator = '&' if '?' in url else '?'
        dest = url + separator + 'options=' + quote('-csearch_path=' + schema)
        env = dict(os.environ, DATABASE_URL=dest)
        cmd = [sys.executable, str(root / 'database/migrate_to_postgres.py'), str(source)]
        subprocess.run(cmd, env=env, cwd=root, check=True, capture_output=True)
        again = subprocess.run(cmd, env=env, cwd=root, capture_output=True)
        assert again.returncode != 0 and b'refusing to overwrite' in again.stderr
        target = psycopg2.connect(dest)
        with target, target.cursor() as c:
            c.execute('SELECT id,user_id FROM addresses'); assert c.fetchall() == [(7, 42)]
            c.execute("INSERT INTO users(name,role) VALUES('Next','customer') RETURNING id")
            assert c.fetchone()[0] > 42
        target.close()
    finally:
        with pg.cursor() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        pg.close()
