"""iPhone install assets, privacy-safe cache policy and same-origin routing."""
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_all_icons_are_served():
    with TestClient(app) as client:
        response = client.get('/manifest.webmanifest')
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('application/manifest+json')
        manifest = response.json()
        assert manifest['start_url'] == '/'
        assert manifest['scope'] == '/'
        assert manifest['display'] == 'standalone'
        assert manifest['id'] == '/'
        for icon in manifest['icons']:
            image = client.get(icon['src'])
            assert image.status_code == 200
            assert image.headers['content-type'] == 'image/png'
            assert image.content.startswith(b'\x89PNG')
        assert client.get('/icons/apple-touch-icon.png').status_code == 200


def test_shell_and_worker_have_update_headers():
    with TestClient(app) as client:
        for path in ['/', '/?utm_source=chatgpt.com', '/sw.js', '/pwa.js']:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-cache'
            assert response.headers['x-content-type-options'] == 'nosniff'
        assert client.get('/api/health').headers['cache-control'] == 'no-store'
        assert client.get('/data/lottery.db').status_code == 404


def test_api_results_are_never_cacheable():
    with TestClient(app) as client:
        response = client.post('/api/predict', json={'count': 1, 'samples': 30})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['mode'] == 'SYNTHETIC_DEMO'


def test_ios_install_metadata_and_safe_area():
    with TestClient(app) as client:
        html = client.get('/').text
    for value in ['viewport-fit=cover', 'apple-mobile-web-app-capable',
                  '/manifest.webmanifest', '/icons/apple-touch-icon.png',
                  'safe-area-inset-top', 'safe-area-inset-bottom',
                  'id="pwa-install-guide"', 'ホーム画面に追加']:
        assert value in html


def test_api_is_excluded_from_worker_and_csv_not_cached():
    worker = (ROOT / 'web/sw.js').read_text()
    assert "url.pathname.startsWith('/api/')" in worker
    assert "request.method !== 'GET'" in worker
    assert "url.origin !== self.location.origin" in worker
    assert "url.pathname === '/'" in worker
    assert "cacheKey = navigation ? '/'" in worker
    assert 'ACTIVATE_UPDATE' in worker
