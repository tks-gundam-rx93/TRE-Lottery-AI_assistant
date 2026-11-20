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

def test_gif_haro_interface_and_assets_served():
    """HTMLとGIF・WebPが同じAPIサーバーから配信されること。"""
    page = client.get("/")
    assert page.status_code == 200
    for name in ("green", "orange", "purple"):
        assert f'id="pod-{name}"' in page.text
    assert 'id="pod-blue"' not in page.text
    assert '<svg class="haro-vector"' not in page.text
    assert 'src="/assets/haro-idle.webp"' in page.text
    assert "class HaroGifPlaybackController" in page.text

    gif = client.get("/assets/haro-speaking.gif")
    fast = client.get("/assets/haro-speaking-fast.gif")
    idle = client.get("/assets/haro-idle.webp")
    assert gif.status_code == fast.status_code == 200
    assert gif.headers['content-type'].startswith('image/gif')
    assert fast.headers['content-type'].startswith('image/gif')
    assert gif.content[:6] == fast.content[:6] == b"GIF89a"
    assert len(gif.content) == len(fast.content)
    assert idle.status_code == 200
    assert idle.content[:4] == b"RIFF"
    assert idle.content[8:12] == b"WEBP"


def test_additional_predictions_use_bundled_history_and_respect_game_format():
    for game, size, upper in [('LOTO6', 6, 43), ('NUMBERS4', 4, 9)]:
        response = client.post('/api/predict', json={'game': game, 'count': 10})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['game'] == game
        assert result['mode'] == 'BUNDLED_CSV'
        assert result['debate'] is None
        picks = [tuple(item['numbers']) for item in result['candidates']]
        assert len(picks) == len(set(picks)) == 10
        assert all(len(pick) == size for pick in picks)
        if game == 'LOTO6':
            assert all(1 <= pick[0] and pick[-1] <= upper for pick in picks)
            assert all(pick == tuple(sorted(set(pick))) for pick in picks)
        else:
            assert all(0 <= digit <= upper for pick in picks for digit in pick)
            assert any(pick[0] == 0 for pick in picks)
