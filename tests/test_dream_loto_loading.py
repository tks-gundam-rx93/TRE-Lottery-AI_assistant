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
    assert "const loader=game==='LOTO7'?window.dreamLotoLoader:null" in html
    assert "loader?.show()" in html
    assert "await loader.reveal(data.candidates[0].numbers)" in html
    assert "loader?.hide()" in html
    assert "requestLottery('/api/predict',game,{" in html
    assert "count,samples:180" in html
    assert "renderPrediction(data)" in html
    assert "openPredictionModal()" in html


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
