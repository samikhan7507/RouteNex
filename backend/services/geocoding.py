"""India place autocomplete via Photon, with a small offline landmark fallback.

The public Photon service is a best-effort demo, not a production SLA. Calls are
serialized and paced per process; configure a private Photon service for scale.
"""
import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

from services.places import PLACES

# Name, latitude, longitude, context, aliases. These are deliberately limited;
# they are a fallback rather than a complete gazetteer of Rajasthan or India.
LANDMARKS = [
    (n, lat, lon, 'Jaipur, Rajasthan', aliases) for n, lat, lon, aliases in PLACES
] + [
    ('Jaipur', 26.9124, 75.7873, 'Rajasthan', []),
    ('Hawa Mahal', 26.9239, 75.8267, 'Jaipur, Rajasthan', ['palace of winds']),
    ('Jal Mahal', 26.9535, 75.8464, 'Jaipur, Rajasthan', []),
    ('City Palace Jaipur', 26.9258, 75.8237, 'Jaipur, Rajasthan', []),
    ('Nahargarh Fort', 26.9373, 75.8156, 'Jaipur, Rajasthan', []),
    ('Jodhpur', 26.2389, 73.0243, 'Rajasthan', []),
    ('Mehrangarh Fort', 26.2980, 73.0187, 'Jodhpur, Rajasthan', []),
    ('Udaipur', 24.5854, 73.7125, 'Rajasthan', []),
    ('City Palace Udaipur', 24.5760, 73.6835, 'Udaipur, Rajasthan', []),
    ('Jaisalmer', 26.9157, 70.9083, 'Rajasthan', []),
    ('Jaisalmer Fort', 26.9124, 70.9120, 'Jaisalmer, Rajasthan', []),
    ('Ajmer', 26.4499, 74.6399, 'Rajasthan', []),
    ('Ajmer Sharif Dargah', 26.4564, 74.6288, 'Ajmer, Rajasthan', []),
    ('Pushkar', 26.4899, 74.5511, 'Rajasthan', []),
    ('Kota', 25.2138, 75.8648, 'Rajasthan', []),
    ('Bikaner', 28.0229, 73.3119, 'Rajasthan', []),
    ('Mount Abu', 24.5926, 72.7156, 'Rajasthan', []),
    ('Chittorgarh Fort', 24.8887, 74.6451, 'Chittorgarh, Rajasthan', []),
    ('Ranthambore National Park', 26.0173, 76.5026, 'Sawai Madhopur, Rajasthan', []),
    ('Bharatpur', 27.2152, 77.5030, 'Rajasthan', []),
    ('Alwar', 27.5530, 76.6346, 'Rajasthan', []),
    ('Delhi', 28.6139, 77.2090, 'Delhi', ['new delhi']),
    ('Taj Mahal', 27.1751, 78.0421, 'Agra, Uttar Pradesh', []),
    ('Agra', 27.1767, 78.0081, 'Uttar Pradesh', []),
    ('Mumbai', 19.0760, 72.8777, 'Maharashtra', ['bombay']),
    ('Ahmedabad', 23.0225, 72.5714, 'Gujarat', []),
    ('Golden Temple', 31.6200, 74.8765, 'Amritsar, Punjab', []),
]

_lock = threading.Lock()
_cache = OrderedDict()
_last_request = 0.0
_CACHE_SECONDS = 600


def _local(q):
    words = q.casefold().split()
    out = []
    for name, lat, lng, context, aliases in LANDMARKS:
        text = ' '.join([name, context] + aliases).casefold()
        if all(word in text for word in words):
            out.append({'name': name, 'label': f'{name}, {context}', 'lat': lat, 'lng': lng})
    return out[:8]


def _parse(data):
    out, seen = [], set()
    features = data.get('features', []) if isinstance(data, dict) else []
    if not isinstance(features, list):
        return []
    for feature in features[:30]:
        try:
            p = feature['properties']; geometry = feature['geometry']
            if not isinstance(p, dict) or geometry.get('type') != 'Point':
                continue
            if str(p.get('countrycode', '')).upper() != 'IN':
                continue
            lng, lat = map(float, geometry['coordinates'][:2])
            if not math.isfinite(lat) or not math.isfinite(lng) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue
            name = p.get('name') or p.get('street') or p.get('city')
            if not isinstance(name, str) or not name.strip():
                continue
            parts = []
            for value in (name, p.get('street'), p.get('district'), p.get('city'), p.get('state'), p.get('country')):
                if isinstance(value, str):
                    value = ' '.join(value.split())
                    if value and value.casefold() not in {v.casefold() for v in parts}:
                        parts.append(value)
            label = ', '.join(parts)[:200]
            key = (label.casefold(), round(lat, 5), round(lng, 5))
            if key not in seen:
                seen.add(key); out.append({'name': name[:120], 'label': label, 'lat': lat, 'lng': lng})
            if len(out) == 8:
                break
        except (TypeError, KeyError, ValueError, AttributeError):
            continue
    return out


def search(query):
    """Return results and status; never cache failures as successful results."""
    global _last_request
    q = ' '.join(query.split())
    fallback = _local(q)
    if os.getenv('ROUTENEX_OFFLINE', '').lower() in ('1', 'true', 'yes', 'on'):
        return {'results': fallback, 'source': 'limited'}
    # Avoid building an unbounded request queue when the provider is slow.
    if not _lock.acquire(timeout=0.2):
        return {'results': fallback, 'source': 'limited'}
    try:
        now = time.monotonic(); key = q.casefold()
        cached = _cache.get(key)
        if cached and now - cached[0] < _CACHE_SECONDS:
            _cache.move_to_end(key)
            return {'results': cached[1], 'source': 'photon'}
        wait = 1.1 - (now - _last_request)
        if wait > 0:
            time.sleep(wait)
        base = os.getenv('PHOTON_URL', 'https://photon.komoot.io/api').strip()
        params = urllib.parse.urlencode({'q': q, 'countrycode': 'IN', 'lat': 26.9124, 'lon': 75.7873, 'limit': 15, 'lang': 'en'})
        request = urllib.request.Request(base + ('&' if '?' in base else '?') + params,
                                         headers={'User-Agent': 'RouteNex/1.0 (place autocomplete)', 'Accept': 'application/json'})
        _last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                raw = response.read(512_001)
            if len(raw) > 512_000:
                raise ValueError('Response too large')
            result = _parse(json.loads(raw))
        except (OSError, ValueError, TypeError):
            return {'results': fallback, 'source': 'limited'}
        # Keep local aliases useful while prioritizing real, disambiguated results.
        seen = {(r['label'].casefold(), round(r['lat'], 4), round(r['lng'], 4)) for r in result}
        for r in fallback:
            key_r = (r['label'].casefold(), round(r['lat'], 4), round(r['lng'], 4))
            if key_r not in seen and len(result) < 8:
                result.append(r); seen.add(key_r)
        _cache[key] = (time.monotonic(), result)
        while len(_cache) > 128:
            _cache.popitem(last=False)
        return {'results': result, 'source': 'photon'}
    finally:
        _lock.release()
