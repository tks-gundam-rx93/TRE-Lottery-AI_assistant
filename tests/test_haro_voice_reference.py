"""参考画像を基準にした可動ハッチとWeb Speech APIの連動テスト。"""
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_hinges_have_inner_mechanisms_and_real_rotation():
    html = UI.read_text(encoding="utf-8")
    assert html.count('class="ear-cavity"') == 6
    assert html.count('class="hatch-leaf"') == 6
    assert html.count('class="eye-pair"') == 3
    assert html.count('class="hatch hatch-left"') == 3
    assert html.count('class="hatch hatch-right"') == 3
    assert 'class="ear-mirror"' in html
    assert "hatch-swing-left" in html
    assert "hatch-swing-right" in html
    assert "class HaroVectorMotionController" in html


def test_speech_timing_animation_starts_and_stops():
    html = UI.read_text(encoding="utf-8")
    for required in (
        "utterance.onstart",
        "utterance.onboundary",
        "utterance.onend",
        "_startCadence(rate)",
        "clearInterval(this.pulseTimer)",
        "this._setFace(id,true)",
        "this._setFace(id,false)",
        "setHaroArtSpeaking(id,enabled)",
        ".classList.toggle('speaking'",
        "stage.dataset.speaker=''",
        "function previewHaroMotion()",
        "haroVisual.preview()",
    ):
        assert required in html


def test_voice_controls_remain_available():
    html = UI.read_text(encoding="utf-8")
    for ident in ("voice-pitch", "voice-rate", "voice-chirp", "voice-pitch-label", "voice-rate-label"):
        assert html.count(f'id="{ident}"') == 1
    for method in (
        "armAudio(){", "_chirp(){", "updateSettings(save=true){",
        "restoreSettings(){", "preview(){",
        "tre_haro_voice_settings", "new SpeechSynthesisUtterance",
        "let startGuard=null;", "3500"
    ):
        assert method in html
