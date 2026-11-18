"""ローカルXAMPP/MySQL切替・初回起動画面の回帰テスト。

CI環境にはローカルDBがないためフェイクリポジトリで永続化呼び出しを確認。
"""
import csv
import io
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app, service
from lottery_ai.core import Draw
from lottery_ai.mysql_repository import MySqlSettings, MySqlDrawRepository


def test_mysql_settings_never_require_credentials_in_repository(monkeypatch):
    """秘密のパスワードをソースへ埋め込まず環境変数を参照する。"""
    monkeypatch.setenv("LOTTERY_DB_PASSWORD", "test-only-secret")
    monkeypatch.setenv("LOTTERY_DB_NAME", "tre_lottery")
    settings = MySqlSettings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.password == "test-only-secret"
    assert settings.database == "tre_lottery"
    assert "test-only-secret" not in str(Path("README.md").read_text(encoding="utf-8"))


def test_invalid_mysql_database_name_rejected(monkeypatch):
    monkeypatch.setenv("LOTTERY_DB_NAME", "invalid; DROP TABLE users")
    with pytest.raises(ValueError):
        MySqlSettings.from_env()


def test_mysql_schema_declares_unique_draws_and_prediction_history():
    """MySQL側は同じ回号の重複を防ぎ、予測履歴を独立保存する。"""
    assert "PRIMARY KEY (lottery_type, draw_no)" in MySqlDrawRepository.DRAW_TABLE_SQL
    assert "CREATE TABLE IF NOT EXISTS prediction_runs" in MySqlDrawRepository.PREDICTION_TABLE_SQL
    assert "result_json LONGTEXT" in MySqlDrawRepository.PREDICTION_TABLE_SQL


def test_mysql_api_integration_without_real_db(monkeypatch):
    """MySQLモードでCSV取込と予測結果が永続化層へ送られる。"""

    class FakeMysql:
        def __init__(self):
            self.draws = []
            self.results = []

        def all(self):
            return list(self.draws)

        def upsert(self, draws, source="CSV"):
            existing = {d.draw_no for d in self.draws}
            new = [d for d in draws if d.draw_no not in existing]
            self.draws.extend(new)
            self.draws.sort(key=lambda d: d.draw_no)
            return len(new)

        def save_prediction(self, prediction):
            self.results.append(prediction)
            return "deadbeef" * 4

    fake = FakeMysql()
    monkeypatch.setattr(service, "mysql", fake)
    client = TestClient(app)

    empty = client.get("/api/health").json()
    assert empty["database"]["backend"] == "mysql"
    assert empty["database"]["status"] == "connected"
    assert empty["database"]["draw_count"] == 0
    assert empty["history_mode"] == "SYNTHETIC_DEMO"

    data = io.StringIO()
    writer = csv.writer(data)
    writer.writerow(["draw_no", "draw_date", *[f"n{i}" for i in range(1, 8)]])
    rng = random.Random(106)
    for number in range(1, 23):
        writer.writerow([number, "2026-01-01", *sorted(rng.sample(range(1, 38), 7))])

    body = data.getvalue().encode("utf-8")
    first = client.post("/api/history/upload", content=body)
    assert first.status_code == 200, first.text
    assert first.json()["mode"] == "MYSQL"
    assert first.json()["inserted"] == 22
    assert first.json()["session"] is None
    second = client.post("/api/history/upload", content=body)
    assert second.status_code == 200
    assert second.json()["inserted"] == 0

    response = client.post("/api/predict", json={"count": 2, "samples": 30})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "MYSQL"
    assert result["last_draw"] == 22
    assert result["prediction_run_id"] == "deadbeef" * 4
    assert len(fake.results) == 1


def test_bootscreen_only_and_exact_first_message():
    """ユーザー操作までメインUIを隠し、指定文言を初回の発話に使う。"""
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    phrase = "3-AIマルチエージェント・システム、起動。メイン・オレンジ、サブ・グリーン、サブ・パープル、同期完了"
    assert '<body class="boot-locked">' in html
    assert 'id="boot-screen"' in html
    assert 'id="boot-launch"' in html
    assert 'onclick="bootHaroSystem()"' in html
    assert phrase in html
    assert "haroSpeech.say(startupMessage,'orange')" in html
    assert "document.body.classList.remove('boot-locked')" in html
    assert "void initializeHaroSystem()" in html
    assert "window.addEventListener('DOMContentLoaded',async()=>{" not in html


def test_local_mysql_credential_file_ignored():
    ignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "config/local.env.cmd" in ignore
    assert Path("scripts/setup_local_mysql.sql").is_file()
    assert Path("scripts/start_local.cmd").is_file()
