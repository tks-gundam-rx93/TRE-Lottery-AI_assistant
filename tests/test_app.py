"""公開デモのHTTPエンドポイントの統合テスト。"""
import csv
import io
import random
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health():
    assert client.get('/api/health').json()['status'] == 'ok'


def test_demo_prediction_is_labelled():
    response = client.post('/api/predict', json={'count': 5, 'samples': 40})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['mode'] == 'SYNTHETIC_DEMO'
    assert len(data['candidates']) == 5
    assert data['training']['validation_samples'] > 0
    assert len(data['debate']['first_round']) == 3
    assert len(data['debate']['second_round']) == 3
    assert all(len(c['numbers']) == 7 and len(set(c['numbers'])) == 7 for c in data['candidates'])


def test_upload_invalid_csv():
    r = client.post('/api/history/upload', content=b'a,b\n1,2\n', headers={'content-type':'text/csv'})
    assert r.status_code == 422


def test_upload_and_predict_session():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['draw_no','draw_date',*[f'n{i}' for i in range(1, 8)]])
    rng = random.Random(2026)
    for i in range(1, 84):
        writer.writerow([i, '2026-01-01', *sorted(rng.sample(range(1, 38), 7))])
    data = buf.getvalue().encode('utf-8')
    r = client.post('/api/history/upload', content=data, headers={'content-type':'text/csv'})
    assert r.status_code == 200, r.text
    session = r.json()['session']
    pred = client.post('/api/predict', json={'count':1,'samples':40,'session':session})
    assert pred.status_code == 200, pred.text
    assert pred.json()['mode'] == 'UPLOADED_CSV'
    assert pred.json()['last_draw'] == 83


def test_expired_session_rejected():
    r = client.post('/api/predict', json={'session':'invalid-session'})
    assert r.status_code == 404


def test_invalid_bounds():
    assert client.post('/api/predict', json={'count': 999}).status_code == 422

def test_haro_approved_artwork_is_served():
    """承認画像をFastAPIで直接配信し、開閉アセットが存在することを検証。"""
    for name in ("haro-approved.webp", "haro-open.webp", "haro-closed-stage.webp"):
        response = client.get("/assets/" + name)
        assert response.status_code == 200
        assert response.content[:4] == b"RIFF"
        assert response.content[8:12] == b"WEBP"
    html = client.get("/")
    assert html.status_code == 200
    assert 'src="/assets/haro-approved.webp"' in html.text
    assert 'id="pod-purple"' in html.text
    assert 'id="pod-blue"' not in html.text
