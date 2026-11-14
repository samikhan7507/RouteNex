"""Fresh demo starts must provide the advertised accounts without resetting users."""
from services import bootstrap
from security import hash_password, verify_password


def test_demo_customer_created_and_can_log_in(client, sql):
    bootstrap.ensure_demo_data()
    response = client.post('/api/auth/login', json={'email': 'customer@routenex.in', 'password': 'Demo@123'})
    assert response.status_code == 200
    assert response.json()['user']['role'] == 'customer'
    assert sql("SELECT count(*) FROM audit_logs WHERE action='LOGIN' AND user_id=?", (response.json()['user']['id'],))[0][0] == 1
    driver = client.post('/api/auth/login', json={'email': 'driver@routenex.in', 'password': 'Demo@123'})
    headers = {'Authorization': 'Bearer ' + driver.json()['access_token']}
    assert client.get('/api/driver/earnings', headers=headers).status_code == 200


def test_bootstrap_does_not_reset_or_reactivate_existing_customer(sql):
    password = hash_password('changed-password')
    sql("INSERT INTO users(name,email,password_hash,role,active) VALUES('Existing','customer@routenex.in',?,'customer',0)", (password,))
    bootstrap.ensure_demo_data()
    bootstrap.ensure_demo_data()
    row = sql("SELECT password_hash,active FROM users WHERE email='customer@routenex.in'")[0]
    assert row['active'] == 0 and verify_password('changed-password', row['password_hash'])
