from datetime import datetime, timezone


def test_successful_logins_are_stored_with_users_and_utc_time(client, auth, sql):
    before = datetime.now(timezone.utc).timestamp()
    # Failed attempts must not be represented as successful LOGIN records.
    assert client.post('/api/auth/login', json={'email': 'c1@test.in', 'password': 'wrong'}).status_code == 401
    assert not sql("SELECT id FROM audit_logs WHERE action='LOGIN' AND user_id=1")
    password = client.post('/api/auth/login', json={'email': 'c1@test.in', 'password': 'Demo@123'})
    assert password.status_code == 200
    assert client.post('/api/auth/otp/request', json={'phone': '8882846897'}).status_code == 200
    otp = client.post('/api/auth/otp/verify', json={'phone': '8882846897', 'code': '123456'})
    assert otp.status_code == 200
    google = client.post('/api/auth/google', json={})
    assert google.status_code == 200
    after = datetime.now(timezone.utc).timestamp()
    records = sql("SELECT a.user_id,a.entity_id,a.details,a.created_at,u.name,u.email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id WHERE a.action='LOGIN' ORDER BY a.id")
    assert len(records) == 3
    assert [r['user_id'] for r in records] == [1, 1, google.json()['user']['id']]
    assert [r['details'] for r in records] == ['', 'OTP', 'Google demo']
    assert all(str(r['user_id']) == r['entity_id'] for r in records)
    assert records[0]['name'] == 'Cust1' and records[0]['email'] == 'c1@test.in'
    for row in records:
        stamp = datetime.fromisoformat(row['created_at'])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        # SQLite stores whole seconds.
        assert before - 1 <= stamp.timestamp() <= after + 1
    admin = auth('admin@test.in')
    data = client.get('/api/audit', headers=admin)
    assert data.status_code == 200
    customer = next(r for r in data.json() if r['action'] == 'LOGIN' and r['user_id'] == 1)
    assert customer['name'] == 'Cust1' and customer['user_email'] == 'c1@test.in' and customer['user_role'] == 'customer'
    assert client.get('/api/audit', headers={'Authorization':'Bearer ' + password.json()['access_token']}).status_code == 403
