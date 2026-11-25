"""4つの候補生成方式のSCAN可視化アセットと連携の回帰テスト。"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "index.html"
JS = ROOT / "web" / "assets" / "algorithm_loading.js"
CSS = ROOT / "web" / "assets" / "algorithm_loading.css"


def test_four_strategy_visual_assets_and_scan_lifecycle():
    html = HTML.read_text(encoding="utf-8")
    assert JS.is_file() and CSS.is_file()
    assert '<link rel="stylesheet" href="/assets/algorithm_loading.css">' in html
    assert '<script src="/assets/algorithm_loading.js"></script>' in html
    assert html.index('src="/assets/dream_loto_loading.js"') < html.index(
        'src="/assets/algorithm_loading.js"'
    )
    assert "window.dreamLotoLoader.show();window.dreamLotoAlgorithms.begin()" in html
    assert "window.dreamLotoAlgorithms.resolve(d);" in html
    assert "await window.dreamLotoLoader.reveal(d.candidates[0].numbers)" in html
    assert "finally{window.dreamLotoAlgorithms.end();window.dreamLotoLoader.hide()" in html
    assert "fetch('/api/predict'" in html
    assert "renderPrediction(d)" in html
    assert "openLoto7Modal()" in html


def test_four_algorithms_have_distinct_visualizations_and_labeled_modes():
    src = JS.read_text(encoding="utf-8")
    for name in ("FREQUENCY", "GAP_PAIR", "MONTE_CARLO", "DEEP_LEARNING"):
        assert src.count(name) >= 2
    for graph in ("frequency(ctx,t)", "gapPair(ctx,t)", "monteCarlo(ctx,t)", "mlp(ctx,t)"):
        assert graph in src
    assert "計算イメージ" in src
    assert "実際の進捗率・並列処理を示しません" in src
    assert "new Set(c.numbers).size===7" in src
    assert "c.numbers.every(n=>Number.isInteger(n)&&n>=1&&n<=37)" in src
    assert "candidate.numbers.map(" in src
    assert "const all=Array.isArray(result&&result.all_candidates)" in src
    assert "履歴不足などで対象外" in src
    assert "requestAnimationFrame" in src
    assert "prefers-reduced-motion" in src
    assert "fetch(" not in src  # 既存のFastAPI予測結果だけを利用する


def test_mobile_layout_and_reduced_motion():
    src = CSS.read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(4" in src
    assert "grid-template-columns: repeat(2" in src
    assert "prefers-reduced-motion: reduce" in src
    assert "min-width: 0" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="Nodeが存在しません")
def test_algorithm_animation_script_is_valid_javascript():
    subprocess.run(
        ["node", "--check", str(JS)],
        check=True, capture_output=True, text=True
    )
