PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, phone TEXT UNIQUE, password_hash TEXT, role TEXT NOT NULL CHECK(role IN ('customer','driver','dispatcher','fleet_manager','admin')), active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS otp_codes(id INTEGER PRIMARY KEY, phone TEXT, code_hash TEXT, expires_at INTEGER, consumed INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS addresses(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), label TEXT, line1 TEXT, city TEXT, state TEXT, pincode TEXT, lat REAL, lng REAL);
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, price REAL, stock INTEGER, icon TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), address_id INTEGER REFERENCES addresses(id), status TEXT DEFAULT 'placed', priority INTEGER DEFAULT 1, delivery_window TEXT, total REAL, lat REAL, lng REAL, route_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), item_id INTEGER REFERENCES items(id), quantity INTEGER, unit_price REAL);
CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY, plate TEXT UNIQUE, type TEXT, capacity_kg REAL, available INTEGER DEFAULT 1, status TEXT DEFAULT 'available', lat REAL, lng REAL, documents TEXT, next_maintenance TEXT, cost_per_km REAL DEFAULT 10);
CREATE TABLE IF NOT EXISTS drivers(id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE REFERENCES users(id), license TEXT, capacity_rating REAL, available INTEGER DEFAULT 1, status TEXT DEFAULT 'available', lat REAL, lng REAL, documents TEXT, vehicle_id INTEGER REFERENCES vehicles(id));
CREATE TABLE IF NOT EXISTS rides(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), driver_id INTEGER REFERENCES drivers(id), pickup TEXT, pickup_lat REAL, pickup_lng REAL, dropoff TEXT, drop_lat REAL, drop_lng REAL, distance_km REAL, fare REAL, eta_min INTEGER, status TEXT DEFAULT 'searching', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS routes(id INTEGER PRIMARY KEY, vehicle_id INTEGER REFERENCES vehicles(id), driver_id INTEGER REFERENCES drivers(id), status TEXT DEFAULT 'planned', distance_km REAL, duration_min INTEGER, cost REAL, geometry TEXT, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS route_orders(route_id INTEGER REFERENCES routes(id), order_id INTEGER UNIQUE REFERENCES orders(id), stop_sequence INTEGER, eta TEXT, PRIMARY KEY(route_id,order_id));
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, type TEXT, severity TEXT, message TEXT, entity_type TEXT, entity_id INTEGER, acknowledged INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS maintenance(id INTEGER PRIMARY KEY, vehicle_id INTEGER REFERENCES vehicles(id), description TEXT, scheduled_for TEXT, status TEXT DEFAULT 'scheduled', cost REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, entity TEXT, entity_id TEXT, details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, message TEXT, read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
-- Phase 0: indexes for the queries the API runs most (safe to re-run)
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, priority);
CREATE INDEX IF NOT EXISTS idx_orders_route ON orders(route_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_rides_user ON rides(user_id, status);
CREATE INDEX IF NOT EXISTS idx_rides_driver ON rides(driver_id, status);
CREATE INDEX IF NOT EXISTS idx_routes_vehicle ON routes(vehicle_id, status);
CREATE INDEX IF NOT EXISTS idx_routes_driver ON routes(driver_id);
CREATE INDEX IF NOT EXISTS idx_drivers_avail ON drivers(available, status);
CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_codes(phone, consumed);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(id DESC);

-- ===== Phase 2: parcels, payments, wallet, coupons (new columns on old tables are added by db.migrate) =====
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS parcels(ride_id INTEGER PRIMARY KEY REFERENCES rides(id), weight_kg REAL, size TEXT, fragile INTEGER DEFAULT 0, description TEXT, recipient_name TEXT, recipient_phone TEXT, delivery_otp TEXT);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), ref_type TEXT, ref_id INTEGER, amount REAL, method TEXT, kind TEXT DEFAULT 'charge', status TEXT, txn_ref TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS wallet_txns(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), amount REAL, kind TEXT, note TEXT, balance_after REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS coupons(code TEXT PRIMARY KEY, title TEXT, scope TEXT DEFAULT 'all', kind TEXT, value REAL, max_discount REAL, min_amount REAL DEFAULT 0, one_time INTEGER DEFAULT 0, expires_at INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS coupon_uses(code TEXT, user_id INTEGER, ref_type TEXT, ref_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_payments_ref ON payments(ref_type, ref_id);
CREATE INDEX IF NOT EXISTS idx_wallet_user ON wallet_txns(user_id, id);
CREATE INDEX IF NOT EXISTS idx_coupon_uses ON coupon_uses(code, user_id);

-- ===== Phase 5: assistant actions (nothing the assistant proposes runs until the user confirms) =====
CREATE TABLE IF NOT EXISTS assistant_actions(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), action TEXT, args TEXT, summary TEXT, status TEXT DEFAULT 'pending', result TEXT, expires_at INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_assistant_user ON assistant_actions(user_id, status);
