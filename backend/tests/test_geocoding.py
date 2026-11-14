import io
import json
from urllib.parse import parse_qs, urlparse

from services import geocoding
from routers import geocoding as router


def feature(name, lat, lon, city='Jaipur', state='Rajasthan', country='IN'):
    return {'properties': {'name': name, 'city': city, 'state': state, 'country': 'India', 'countrycode': country},
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]}}


def test_offline_landmarks_and_api_validation(client, auth):
    router.limiter.hits.clear()
    headers = auth('c1@test.in')
    assert client.get('/api/places/search?q=udaipur', headers=headers).json()['results'][0]['label'] == 'Udaipur, Rajasthan'
    assert any('Taj Mahal' in x['label'] for x in client.get('/api/places/search?q=taj', headers=headers).json()['results'])
    assert client.get('/api/places/search?q=xx', headers=headers).status_code == 422
    assert client.get('/api/places/search?q=+++', headers=headers).status_code == 400
    assert client.get('/api/places/search?q=jaipur').status_code == 401


def test_remote_search_parses_india_and_reuses_cache(monkeypatch):
    monkeypatch.delenv('ROUTENEX_OFFLINE', raising=False)
    geocoding._cache.clear(); geocoding._last_request = 0
    calls = []
    body = {'features': [feature('Lake Palace', 24.576, 73.68, 'Udaipur'), feature('Taj Mahal', 27.17, 78.04, 'Agra', 'Uttar Pradesh'),
                         feature('Not India', 51.5, 0, 'London', 'England', 'GB'), feature('Bad coords', float('nan'), 75), {'bad': 1}]}
    def fake(req, timeout):
        calls.append(req.full_url); assert timeout == 4
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(geocoding.urllib.request, 'urlopen', fake)
    result = geocoding.search('palace')
    assert result['source'] == 'photon'
    assert [r['name'] for r in result['results'][:2]] == ['Lake Palace', 'Taj Mahal']
    assert all(r['name'] not in ('Not India', 'Bad coords') for r in result['results'])
    params = parse_qs(urlparse(calls[0]).query)
    assert params['countrycode'] == ['IN'] and params['q'] == ['palace']
    assert geocoding.search('palace') == result and len(calls) == 1


def test_provider_failure_and_busy_fall_back(monkeypatch):
    monkeypatch.delenv('ROUTENEX_OFFLINE', raising=False)
    geocoding._cache.clear(); geocoding._last_request = 0
    def fail(*args, **kwargs):
        raise OSError('network down')
    monkeypatch.setattr(geocoding.urllib.request, 'urlopen', fail)
    result = geocoding.search('jodhpur')
    assert result['source'] == 'limited' and result['results'][0]['name'] == 'Jodhpur'
    assert not geocoding._cache
    geocoding._lock.acquire()
    try:
        assert geocoding.search('udaipur')['source'] == 'limited'
    finally:
        geocoding._lock.release()
