"""Real-world student catalogue: clean data, safe sync from the old 15-item demo catalogue, weights reach the optimizer."""
from services import catalog


def active(sql):
    return {r["name"] for r in sql("SELECT name FROM items WHERE active=1")}


def test_catalogue_data_is_clean():
    names = [i[1] for i in catalog.ITEMS]
    assert len(names) == len(set(names)) and len(names) >= 100
    assert all(isinstance(i[3], int) and i[3] > 0 and i[4] > 0 and i[0] in catalog.STOCK for i in catalog.ITEMS)
    assert not set(names) & set(catalog.LEGACY)


def test_sync_adds_everything_and_hides_the_old_demo_services(sql):
    sql("INSERT INTO items(name,description,category,price,stock,icon,weight_kg) VALUES('Express Parcel','old','Express',199,5,'P',2)")
    assert catalog.sync() == len(catalog.ITEMS)
    now = active(sql)
    assert "Express Parcel" not in now and {i[1] for i in catalog.ITEMS} <= now
    assert {"Parcel", "Crate"} <= now                                     # items the sync does not know about are left alone
    assert sql("SELECT COUNT(*) FROM items WHERE name='Express Parcel' AND active=0")[0][0] == 1   # hidden, not deleted


def test_sync_twice_changes_nothing_and_keeps_real_stock(sql):
    catalog.sync()
    sql("UPDATE items SET stock=7 WHERE name='Rice, 5 kg'")
    n = sql("SELECT COUNT(*) FROM items")[0][0]
    assert catalog.sync() == 0 and sql("SELECT COUNT(*) FROM items")[0][0] == n
    assert sql("SELECT stock FROM items WHERE name='Rice, 5 kg'")[0][0] == 7


def test_demo_mode_tops_up_nearly_empty_stock(sql):
    catalog.sync()
    sql("UPDATE items SET stock=1 WHERE name='Rice, 5 kg'")
    catalog.sync()                                                         # tests run with DEMO_MODE=true
    assert sql("SELECT stock FROM items WHERE name='Rice, 5 kg'")[0][0] >= 5


def test_items_endpoint_lists_only_active_items(client, sql):
    sql("INSERT INTO items(name,description,category,price,stock,icon,weight_kg) VALUES('Express Parcel','old','Express',199,5,'P',2)")
    catalog.sync()
    names = {i["name"] for i in client.get("/api/items").json()}
    assert "Express Parcel" not in names and "Rice, 5 kg" in names


def test_catalogue_weight_reaches_the_order(client, auth, sql):
    catalog.sync()
    jar = sql("SELECT id FROM items WHERE name='Drinking Water Jar, 20 L'")[0][0]
    r = client.post("/api/orders", headers=auth("c1@test.in"), json={"address_id": 1, "priority": 2, "delivery_window": "18:00-21:00", "items": [{"item_id": jar, "quantity": 2}]})
    assert r.status_code == 200, r.text
    assert sql("SELECT weight_kg FROM orders WHERE id=?", (r.json()["id"],))[0][0] == 42.0
