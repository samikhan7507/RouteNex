"""Selectable place suggestions: curated offline pilot + configurable real geocoder."""
from __future__ import annotations
import difflib
import hashlib
import re
from datetime import timedelta
import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import LocationCache, utcnow

PLACES = [
    ("C-Scheme", 26.9124, 75.7873, "Central Jaipur"), ("Malviya Nagar", 26.8540, 75.8243, "South Jaipur"),
    ("Vaishali Nagar", 26.9126, 75.7442, "West Jaipur"), ("Mansarovar", 26.8505, 75.7628, "South-west Jaipur"),
    ("Jagatpura", 26.8399, 75.8322, "South-east Jaipur"), ("Raja Park", 26.8942, 75.8210, "Central Jaipur"),
    ("Bani Park", 26.9322, 75.7933, "North Jaipur"), ("Tonk Road", 26.8735, 75.7950, "South Jaipur"),
    ("Amer Fort", 26.9855, 75.8513, "Amer, Jaipur"), ("Sitapura Industrial Area", 26.7751, 75.8514, "RIICO, Jaipur"),
    ("Jhotwara", 26.9540, 75.7420, "North-west Jaipur"), ("Civil Lines", 26.9064, 75.7790, "Civil Lines, Jaipur"),
    ("Sindhi Camp Bus Stand", 26.9227, 75.7994, "Transport Nagar, Jaipur"),
    ("World Trade Park", 26.8530, 75.8056, "Malviya Nagar, Jaipur"),
    ("Jaipur Junction Railway Station", 26.9196, 75.7881, "Station Road, Jaipur"),
    ("Jaipur International Airport", 26.8242, 75.8122, "Sanganer, Jaipur"),
    ("Jaipur National University", 26.8434, 75.8640, "Jagatpura, Jaipur"),
    ("Manipal University Jaipur", 26.8437, 75.5656, "Dahmi Kalan, Jaipur"),
    ("Malaviya National Institute of Technology", 26.8638, 75.8108, "JLN Marg, Jaipur"),
    ("Rajasthan University", 26.8844, 75.8107, "JLN Marg, Jaipur"),
    ("Hawa Mahal", 26.9239, 75.8267, "Pink City, Jaipur"), ("City Palace", 26.9258, 75.8237, "Pink City, Jaipur"),
    ("Jantar Mantar", 26.9247, 75.8244, "Pink City, Jaipur"), ("Albert Hall Museum", 26.9117, 75.8195, "Ram Niwas Bagh, Jaipur"),
    ("Nahargarh Fort", 26.9374, 75.8154, "Aravalli Hills, Jaipur"), ("Jaigarh Fort", 26.9858, 75.8456, "Amer, Jaipur"),
    ("Jal Mahal", 26.9535, 75.8460, "Man Sagar Lake, Jaipur"), ("Birla Mandir", 26.8924, 75.8155, "Moti Dungri, Jaipur"),
    ("Govind Dev Ji Temple", 26.9274, 75.8237, "City Palace, Jaipur"), ("Sanganer", 26.8192, 75.7930, "South Jaipur"),
    ("Ajmer Road", 26.9073, 75.7447, "West Jaipur"), ("Sirsi Road", 26.9280, 75.7330, "West Jaipur"),
    ("Mahindra SEZ", 26.8238, 75.6280, "Ajmer Road, Jaipur"), ("Mahatma Gandhi Hospital", 26.7727, 75.8544, "Sitapura, Jaipur"),
    ("SMS Hospital", 26.9064, 75.8167, "JLN Marg, Jaipur"), ("Fortis Hospital", 26.8468, 75.8037, "JLN Marg, Jaipur"),
    ("Narayan Singh Circle", 26.8983, 75.8091, "Central Jaipur"), ("Ajmeri Gate", 26.9159, 75.8195, "Pink City, Jaipur"),
    ("Chandpole", 26.9222, 75.8121, "Pink City, Jaipur"), ("Gandhinagar Railway Station", 26.8928, 75.7938, "Gandhinagar, Jaipur"),
]
ALIASES = {"wtp": "world trade park", "mnit": "malaviya national", "jnu": "jaipur national", "airport": "airport", "station": "jaipur junction", "bus stand": "sindhi camp", "amer": "amer fort", "amber": "amer fort", "mansarover": "mansarovar"}


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", value.lower())).strip()


def local_search(query: str) -> list[dict]:
    q = normalize(query)
    q = ALIASES.get(q, q)
    scored = []
    for i, (name, lat, lng, area) in enumerate(PLACES):
        n = normalize(name)
        score = 100 if n.startswith(q) else 80 if q in n else 0
        if not score:
            ratio = difflib.SequenceMatcher(None, q, n).ratio()
            if ratio >= 0.62:
                score = int(ratio * 60)
        if score:
            scored.append((score, {"id": f"local-{i}", "name": name, "lat": lat, "lng": lng,
                                   "subtitle": f"{area} · Rajasthan, India", "provider": "local"}))
    return [x[1] for x in sorted(scored, key=lambda x: (-x[0], x[1]["name"]))[:6]]


def search(db: Session, query: str) -> dict:
    settings = get_settings()
    q = " ".join(query.split())[:120]
    provider = settings.location_provider
    key = hashlib.sha256(f"{provider}:{q.lower()}".encode()).hexdigest()[:120]
    cached = db.get(LocationCache, key)
    if cached and cached.expires_at > utcnow():
        return {"results": cached.results, "provider": provider, "cached": True}
    if provider == "local":
        results = local_search(q)
    else:
        try:
            if provider == "geoapify":
                r = httpx.get("https://api.geoapify.com/v1/geocode/autocomplete", params={
                    "text": q, "limit": 6, "format": "json", "bias": "proximity:75.7873,26.9124",
                    "apiKey": settings.geoapify_api_key}, timeout=4.0)
                r.raise_for_status()
                results = [{"id": str(x.get("place_id", i)), "name": x.get("name") or x.get("address_line1") or q,
                            "subtitle": x.get("address_line2", "India"), "lat": float(x["lat"]), "lng": float(x["lon"]), "provider": provider}
                           for i, x in enumerate(r.json().get("results", [])) if x.get("lat") is not None and x.get("lon") is not None]
            else:
                if not settings.photon_url:
                    raise HTTPException(503, "Place search is not configured")
                r = httpx.get(settings.photon_url.rstrip("/") + "/api", params={"q": q, "limit": 6, "lat": 26.9124, "lon": 75.7873}, timeout=4.0)
                r.raise_for_status()
                results = []
                for i, f in enumerate(r.json().get("features", [])):
                    p, lng, lat = f.get("properties", {}), *f["geometry"]["coordinates"][:2]
                    results.append({"id": str(p.get("osm_id", i)), "name": p.get("name") or p.get("street") or q,
                                    "subtitle": ", ".join(str(x) for x in [p.get("city"), p.get("state"), p.get("country")] if x),
                                    "lat": lat, "lng": lng, "provider": provider})
        except HTTPException:
            raise
        except Exception:
            # Never silently substitute a different city for a failed real geocoder.
            raise HTTPException(503, "Place search is temporarily unavailable. Try again or pick a saved address")
    if not cached:
        cached = LocationCache(key=key, provider=provider, results=results)
        db.add(cached)
    cached.results, cached.expires_at = results, utcnow() + timedelta(hours=24 if results else 1)
    return {"results": results, "provider": provider, "cached": False}
