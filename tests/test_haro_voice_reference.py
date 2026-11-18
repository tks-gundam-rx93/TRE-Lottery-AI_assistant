"""録画を参考にしたハロ風音声・可動ハッチの回帰テスト。

ブラウザ音声の直接録音はCIで実行できないため、UI構造と実行経路を検証する。
"""
from pathlib import Path
import re

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_reference_style_hatches_all_three_units():
    source = UI.read_text(encoding="utf-8")
    assert source.count('class="ear-hatch ear-hatch-left"') == 3
    assert source.count('class="ear-hatch ear-hatch-right"') == 3
    assert source.count('class="ear-interior ear-interior-left"') == 3
    assert source.count('class="ear-interior ear-interior-right"') == 3
    assert source.count('class="haro-head-assembly"') == 3
    assert source.count('class="voice-eye"') == 6


def test_hinge_rotates_each_side_and_has_audio_fallback():
    source = UI.read_text(encoding="utf-8")
    for rule in (
        "@keyframes haro-hatch-left",
        "@keyframes haro-hatch-right",
        "@keyframes haro-head-motion",
        "@keyframes haro-eye-talk",
        ".haro.speaking .ear-hatch-left",
        ".haro.speaking .ear-hatch-right",
        ".haro.speaking .haro-head-assembly",
        ".haro.speaking .voice-eye",
        "utterance.onboundary",
        "_startCadence(rate)",
        "clearInterval(this.pulseTimer)",
        "@media(prefers-reduced-motion:reduce)",
    ):
        assert rule in source


def test_voice_tuning_controls_and_local_storage():
    source = UI.read_text(encoding="utf-8")
    for ident in ("voice-pitch", "voice-rate", "voice-chirp", "voice-pitch-label", "voice-rate-label"):
        assert source.count(f'id="{ident}"') == 1
    for method in (
        "armAudio(){",
        "_chirp(){",
        "updateSettings(save=true){",
        "restoreSettings(){",
        "preview(){",
        "tre_haro_voice_settings",
        "new SpeechSynthesisUtterance",
        "let startGuard=null;",
        "3500",
        "this._setFace(id,true);",
    ):
        assert method in source
    assert "haroSpeech.armAudio();" in source
    assert "haroSpeech.restoreSettings();" in source
    assert "startupMessage" in source


def test_css_svg_open_and_close_are_independent():
    """耳は左右で反対方向に動き、耳内の機構は閉鎖時にはハッチに覆われる。"""
    source = UI.read_text(encoding="utf-8")
    assert re.search(r"@keyframes haro-hatch-left[\s\S]*?rotate\(71deg\)", source)
    assert re.search(r"@keyframes haro-hatch-right[\s\S]*?rotate\(-73deg\)", source)
    assert ".haro .ear-hatch-left{transform-origin:62px 83px}" in source
    assert ".haro .ear-hatch-right{transform-origin:178px 83px}" in source
