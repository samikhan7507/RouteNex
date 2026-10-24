"""Assistant building blocks that need no web server or database."""
from services import places, kb, llm, assistant as A


def test_places_resolve_aliases_typos_and_unknowns():
    assert places.resolve("the airport")[0] == "Jaipur Airport" and places.resolve("amber fort")[0] == "Amer Fort"
    assert places.resolve("malvia nagar")[0] == "Malviya Nagar" and places.resolve("my house") is None


def test_parse_trip_understands_both_word_orders_and_parcel_details():
    t = A.parse_trip("send a parcel from Malviya Nagar to Amer Fort for Ravi 9876543210 2kg fragile")
    assert (t["pickup"], t["drop"], t["weight_kg"], t["fragile"], t["recipient_phone"], t["recipient_name"]) == ("malviya nagar", "amer fort", 2.0, True, "9876543210", "Ravi")
    r = A.parse_trip("cab to the airport from c-scheme pay with wallet")
    assert places.resolve(r["pickup"])[0] == "C-Scheme" and places.resolve(r["drop"])[0] == "Jaipur Airport" and r["payment_method"] == "wallet"


def test_faq_retrieval_finds_the_right_policy_and_ignores_nonsense():
    assert kb.search("how do I cancel my ride")[0][1] == "cancel-trip" and kb.search("what is the otp")[0][1] == "otp"
    assert kb.search("tell me a joke") == []


def test_offline_router_routes_by_role():
    cust, drv, ops = {"role": "customer", "name": "A B"}, {"role": "driver", "name": "A B"}, {"role": "dispatcher", "name": "A B"}
    assert A.offline_route(cust, "where is my order", [])["tool"] == "track" and A.offline_route(cust, "how do I cancel a ride?", [])["tool"] == "faq"
    assert A.offline_route(cust, "cancel my order 14", [])["args"] == {"kind": "order", "id": 14}
    assert A.offline_route(drv, "how much did I earn", [])["tool"] == "earnings" and A.offline_route(ops, "RJ14-RN-203 broke down", [])["tool"] == "vehicle_breakdown"
    assert A.offline_route(ops, "why is order 28 late", [])["args"] == {"id": 28}


def test_roles_only_see_their_own_tools():
    assert "apply_plan" not in A.allowed_tools("customer") and "book_ride" not in A.allowed_tools("driver") and "book_ride" in A.allowed_tools("customer") and "plan_preview" in A.allowed_tools("admin")


def test_llm_json_is_parsed_leniently_and_pii_is_redacted():
    assert llm.parse_json_loose('Sure!\n```json\n{"tool":"wallet","args":{}}\n```') == {"tool": "wallet", "args": {}}
    r = llm.redact("call 9876543210 or +91 98765 43210, mail a.b@x.com"); assert "9876543210" not in r and "98765 43210" not in r and "@" not in r


def test_llm_args_are_sanitised():
    out = A._sanitize({"id": "#14abc", "weight_kg": "3.5", "evil": {"a": 1}, "x" * 50: "long", "pickup": "  c-scheme  "})
    assert out == {"id": 14, "weight_kg": 3.5, "pickup": "c-scheme"}
