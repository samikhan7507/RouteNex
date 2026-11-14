"""Runs in a subprocess against a disposable PostgreSQL schema."""
import json
from fastapi.testclient import TestClient
from app import app
from db import one

with TestClient(app) as client:
    def post(path, body, headers=None):
        r = client.post(path, json=body, headers=headers or {})
        assert r.status_code == 200, (path, r.status_code, r.text)
        return r.json()
    def get(path, headers=None):
        r = client.get(path, headers=headers or {})
        assert r.status_code == 200, (path, r.status_code, r.text)
        return r.json()
    def login(email, password):
        return {'Authorization': 'Bearer ' + post('/api/auth/login', {'email': email, 'password': password})['access_token']}
    customer = login('customer@routenex.in', 'Demo@123')
    admin = login('admin@test.in', 'owner-pass-123')
    driver = login('driver@routenex.in', 'Demo@123')
    get('/api/driver/earnings', driver)
    trip = post('/api/rides', {'pickup': 'A', 'pickup_lat': 26.9, 'pickup_lng': 75.8,
                                'dropoff': 'B', 'drop_lat': 26.82, 'drop_lng': 75.81}, customer)
    assert trip['timeline'][0]['at']
    get('/api/rides/%s/track' % trip['id'], customer)
    post('/api/rides/%s/cancel' % trip['id'], {}, customer)
    parcel = post('/api/parcels', {'pickup': 'A', 'pickup_lat': 26.9, 'pickup_lng': 75.8,
                                   'dropoff': 'B', 'drop_lat': 26.82, 'drop_lng': 75.81,
                                   'weight_kg': 4, 'size': 'small', 'recipient_name': 'Ravi',
                                   'recipient_phone': '9876543210'}, customer)
    assert parcel['kind'] == 'parcel' and parcel['timeline'][0]['at']
    post('/api/rides/%s/cancel' % parcel['id'], {}, customer)
    get('/api/ml/predictions', admin)
    get('/api/coupons', customer)
    address = post('/api/addresses', {'label': 'Home', 'line1': 'A road', 'city': 'Jaipur', 'state': 'RJ', 'pincode': '302001', 'lat': 26.91, 'lng': 75.79}, customer)
    item = get('/api/items')[0]
    order = post('/api/orders', {'address_id': address['id'], 'items': [{'item_id': item['id'], 'quantity': 1}], 'delivery_window': '08:00-22:00'}, customer)
    assert json.loads(get('/api/orders', customer)[0]['items'])[0]['name'] == item['name']
    result = post('/api/optimizer/run', {}, admin)
    assert result['applied'] and result['routes']
    assert json.loads(get('/api/routes', admin)[0]['stops'])[0]['order_id'] == order['id']
    assert any(u['email'] == 'customer@routenex.in' for u in get('/api/admin/users', admin))
    assert one("SELECT COUNT(*) n FROM audit_logs WHERE action='LOGIN'")['n'] >= 3
# Startup a second time must preserve data and be idempotent.
with TestClient(app) as client:
    assert one('SELECT COUNT(*) n FROM orders')['n'] == 1
