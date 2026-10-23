"""Coarse, opt-in reverse geocoding. Coordinates are never persisted."""
import json, math, os, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_lock = threading.Lock()
_cache = {}
_last = 0.0

def locate(body):
    global _last
    values = []
    for key, limit in [('latitude', 90), ('longitude', 180)]:
        n = body.get(key)
        if type(n) not in (int, float) or not math.isfinite(n) or abs(n) > limit:
            raise ValueError('定位坐标无效，请重新获取。')
        values.append(round(n, 3))
    lat, lon = values
    key = (lat, lon)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1])
        if time.monotonic() - _last < 1.1:
            raise ValueError('定位请求较频繁，请稍后重试。')
        _last = time.monotonic()
        endpoint = os.environ.get('PHM_GEOCODER_URL', 'https://nominatim.openstreetmap.org/reverse')
        query = urlencode({'lat':lat,'lon':lon,'format':'geocodejson','zoom':18,'addressdetails':1,'accept-language':'zh-CN'})
        req = Request(endpoint+'?'+query, headers={'User-Agent':'PingHaoMai/0.2 (https://www.harvey404.com/pinghaomai/)'})
        try:
            with urlopen(req, timeout=12) as response:
                result = json.load(response)
        except Exception:
            raise ValueError('位置地址解析暂不可用，请手动填写城市和地标。') from None
        features = result.get('features') or []
        address = features[0].get('properties', {}).get('geocoding', {}) if features else {}
        city = next((address[k] for k in ('city','town','municipality','county','state') if address.get(k)), '')
        landmark = next((address[k] for k in ('street','locality','district','name') if address.get(k)), '')
        if not city or not landmark:
            raise ValueError('未能识别当前位置的城市和地标，请手动填写。')
        data = {'city':city[:40], 'keyword':landmark[:80], 'source':'© OpenStreetMap contributors · Nominatim'}
        # Keep only a small in-memory cache; no visitor identity or coordinates on disk.
        if len(_cache) >= 256: _cache.clear()
        _cache[key] = (time.monotonic()+3600, data)
        return dict(data)
