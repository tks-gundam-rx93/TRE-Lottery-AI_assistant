"""TiDB接続診断: 公開APIへDB秘密情報を返さないことを確認。"""
from fastapi.testclient import TestClient

from app import app, service, _safe_db_error_code


class BrokenRepo:
    """資格情報を含む例外を発生させる接続失敗のテスト用リポジトリ。"""
    def stats(self):
        raise OSError("certificate verify failed for secret-host.example.org password=NEVER_SHOW")


def test_db_connection_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(service, "mysql", BrokenRepo())
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["database"]["backend"] == "mysql"
    assert data["database"]["status"] == "unavailable"
    assert data["database"]["error_type"] == "OSError"
    assert data["database"]["error_code"] == "tls_certificate"
    text = response.text
    assert "secret-host" not in text
    assert "NEVER_SHOW" not in text
    assert "password" not in text


def test_safe_error_categories_do_not_expose_messages():
    cases = [
        (Exception("Access denied for user 'secret' using password"), "authentication"),
        (Exception("Unknown database private_db"), "database_missing"),
        (Exception("TLS handshake problem"), "tls_handshake"),
        (Exception("getaddrinfo failed: private-hostname"), "dns"),
        (Exception("timed out while connecting secret-host"), "timeout"),
        (Exception(2003, "Can't connect to secret-host"), "network"),
        (Exception(1045, "Access denied for secret"), "authentication"),
    ]
    for exception, expected in cases:
        assert _safe_db_error_code(exception) == expected
