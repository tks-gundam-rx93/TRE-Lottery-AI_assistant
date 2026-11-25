"""PWA用の配信、ホーム画面アイコン、オフライン方針の回帰テスト。

PWAのホーム画面登録操作自体はOSの管理領域のため、iOS実機で行う。
"""
from pathlib import Path
import struct

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_manifest_is_valid_and_installable():
    """アプリ名・起動URL・standalone・192/512のPNGを確認する。"""
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert "application/manifest+json" in response.headers["content-type"]
    config = response.json()
    assert config["name"].startswith("TRE Lottery")
    assert config["start_url"] == "/"
    assert config["scope"] == "/"
    assert config["display"] == "standalone"
    assert config["lang"] == "ja"
    icons = {(entry["src"], entry["sizes"], entry["purpose"]) for entry in config["icons"]}
    assert ("/icons/icon-192.png", "192x192", "any") in icons
    assert ("/icons/icon-512.png", "512x512", "any") in icons
    assert ("/icons/icon-maskable-512.png", "512x512", "maskable") in icons


def test_icons_are_real_pngs_with_expected_dimensions():
    """ホーム画面のアイコンはSVGを装ったテキストではなく本物のPNG。"""
    for filename, expected in (
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("icon-maskable-512.png", 512),
        ("apple-touch-icon.png", 180),
    ):
        response = client.get("/icons/" + filename)
        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]
        assert response.content.startswith(bytes.fromhex("89504e470d0a1a0a"))
        width, height = struct.unpack(">II", response.content[16:24])
        assert (width, height) == (expected, expected)


def test_service_worker_scope_and_no_personal_data_cache():
    """API結果をキャッシュせず、SWの更新検出を妨げない。"""
    response = client.get("/service-worker.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]
    content = response.text
    assert "event.request.method !== 'GET'" in content
    assert "url.pathname.startsWith('/api/')" in content
    assert "if (url.pathname.startsWith('/api/')) return;" in content
    assert "event.request.mode === 'navigate' && url.pathname === '/'" in content
    assert "caches.open(APP_SHELL_CACHE)" in content
    assert "cache.match('/offline.html')" in content
    assert "cache.put(event.request, copy)" in content


def test_boot_screen_and_pwa_links_remain_in_main_ui():
    """PWA化しても初期『AIハロ起動』ボタンの挙動を維持する。"""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    for token in (
        'class="boot-locked"',
        'id="boot-launch"',
        "bootHaroSystem()",
        'href="/manifest.webmanifest"',
        'href="/icons/apple-touch-icon.png"',
        'id="pwa-banner"',
        "class PwaInstallController",
        "navigator.serviceWorker.register('/service-worker.js',{scope:'/'})",
        "ホーム画面に追加",
        "Webアプリとして開く",
        "'/api/predict'",
    ):
        assert token in html


def test_scan_assets_are_precached_with_the_app_shell():
    home = client.get("/").text
    worker = client.get("/service-worker.js").text
    shell = worker.split("const STATIC_SHELL = [", 1)[1].split("];", 1)[0]
    for name in ("dream_loto_loading", "algorithm_loading"):
        for extension in ("css", "js"):
            asset = f"/assets/{name}.{extension}"
            assert asset in home
            assert f"'{asset}'" in shell
            assert client.get(asset).status_code == 200


def test_offline_screen_explains_that_predictions_require_a_server():
    """オフラインで誤った予測を出さないことを表示する。"""
    response = client.get("/offline.html")
    assert response.status_code == 200
    assert "オフライン" in response.text
    assert "予測" in response.text
    assert "サーバー接続が必要" in response.text
    assert client.get("/api/health").json()["status"] == "ok"
