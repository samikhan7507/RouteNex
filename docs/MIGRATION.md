# Migrating v2 (SQLite) → v3 (PostgreSQL)

`scripts/migrate_sqlite.py` is a one-way, transactional importer. The source is opened **read-only**;
the target must be a fresh PostgreSQL database already at Alembic head (`0002`). Run it **before**
`scripts/bootstrap.py`. Dry-run is the default; add `--apply` to write.

```bash
alembic upgrade head
python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db --report migration.json
python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db --apply --report migration.json
python scripts/bootstrap.py        # ensures the configured admin; honors SEED_DEMO_DATA; never deletes data
```

## Table mapping
| v2 | v3 | Notes |
|---|---|---|
| `users` | `users` | wallet REAL rupees → BIGINT paise; email normalised |
| `addresses` | `addresses` | missing coords/pincode defaulted and reported |
| `items` | `products` | generates `LEGACY-*` SKU/slug; price → paise; weight kg → grams |
| `orders` | `orders` | total/discount → paise; free-text window → IST timestamps |
| `order_items` | `order_items` | denormalised product name/SKU/weight |
| `vehicles` | `vehicles` | cost/km → paise |
| `drivers` | `drivers` | `license` → `license_number`, `capacity_rating` → `rating` |
| `rides` + `parcels` | `trips` | `arriving` → `arrived`; OTPs rotated to encrypted 6-digit codes |
| `routes` | `routes` | geometry JSON; cost → paise |
| `route_orders` | `route_stops` | sequences renumbered per route |
| `payments` | `payments` (+ `refunds`) | zero-amount rows skipped; refunds linked to original charge |
| `wallet_txns` | `wallet_transactions` | signed paise ledger |
| `coupons` / `coupon_uses` | `coupons` / `coupon_uses` | percent value vs flat paise; `ride` refs → `trip` |
| `alerts` | `alerts` | |
| `notifications` | `notifications` | `message` → `body` |
| `audit_logs` | `audit_logs` | `user_id` → `actor_id`; non-JSON details wrapped |
| `maintenance` | `maintenance_records` | cost → paise |
| `assistant_actions` | `assistant_actions` | pending actions skipped (never auto-executed) |
| `otp_codes` | — | intentionally not migrated; users request fresh OTPs |

## Guarantees & reported assumptions
- All-or-nothing transaction; sequences are reset to `MAX(id)` after import.
- Refuses non-empty targets, unknown statuses/payment methods, missing FKs, and double-booked active
  routes/drivers (resolve these in v2 first).
- Reports counts, skipped rows and assumptions: defaulted delivery windows/coordinates, dropped
  orphan route links, rotated handover OTPs, skipped zero-amount payments and pending assistant actions.
- Password hashes are preserved; legacy PBKDF2 hashes upgrade to argon2id on next successful login.

## After migration
1. Run `python scripts/bootstrap.py` (and `--catalog` only if you want the v3 starter catalogue added
   alongside imported products).
2. Start the API and worker; run `python tools/preflight.py`.
3. Verify wallet balances, order/trip totals and audit history against the JSON report.
