"""夢ロトくん風SCAN演出の配信・API連動・構文・回帰テスト。"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "index.html"
SCRIPT = ROOT / "web" / "assets" / "dream_loto_loading.js"
STYLE = ROOT / "web" / "assets" / "dream_loto_loading.css"


def test_loading_assets_are_published_and_wired_into_scan():
    html = HTML.read_text(encoding="utf-8")
    assert SCRIPT.is_file() and STYLE.is_file()
    assert '<script src="/assets/dream_loto_loading.js"></script>' in html
    assert '<link rel="stylesheet" href="/assets/dream_loto_loading.css">' in html
    assert "window.dreamLotoLoader.show()" in html
    assert "await window.dreamLotoLoader.reveal(d.candidates[0].numbers)" in html
    assert "window.dreamLotoLoader.hide();btn.disabled=false" in html
    # 既存API・予測リクエスト・5候補出力を変更しないこと。
    assert "fetch('/api/predict'" in html
    assert "body:JSON.stringify({count:5,samples:180" in html
    assert "renderPrediction(d)" in html
    assert "openLoto7Modal()" in html


def test_scan_animation_exposes_clear_non_real_draw_disclaimer_and_validates_api_result():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "const MAX_NUMBER = 37;" in script
    assert "const MAIN_COUNT = 7;" in script
    assert "async reveal(numbers)" in script
    assert "new Set(numbers).size !== MAIN_COUNT" in script
    assert "n < 1 || n > MAX_NUMBER" in script
    assert "this.reducedMotion" in script
    assert "37球を攪拌中" in script
    assert "遠心回転盤から本数字を抽出" in script
    assert "実際の抽せん・当せんを再現するものではありません" in script
    # 外部画像やAPIへの追加リクエストを発生させない。
    assert "fetch(" not in script
    assert "Math.random() * (i + 1)" in script  # 抽出順だけをシャッフル


def test_dream_loto_javascript_parses_in_node_if_available():
    node = shutil.which("node")
    if not node:
        pytest.skip("nodeが無い実行環境のため構文確認をスキップ")
    subprocess.run([node, "--check", str(SCRIPT)], check=True, capture_output=True)
