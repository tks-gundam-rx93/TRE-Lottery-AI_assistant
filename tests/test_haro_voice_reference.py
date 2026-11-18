"""承認された開閉画像と音声連動の回帰テスト（外部マイク・TTSに依存しない）。"""
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_artwork_open_closed_uses_approved_frames():
    """承認デザインの画像を開閉状態に使用し、物理ヒンジの実装と偽らない。"""
    source = UI.read_text(encoding="utf-8")
    assert source.count('src="/assets/haro-approved.webp"') == 1
    assert source.count('src="/assets/haro-closed-stage.webp"') == 1
    assert "transition:opacity .68s" in source
    assert "class=\"haro-art-stage ears-open\"" in source
    assert 'id="haro-ear-state"' in source
    assert "EAR STATE: " in source


def test_voice_timing_moves_reference_art():
    """Web Speech発話開始・境界・終了で開耳画像と目の発光を制御する。"""
    source = UI.read_text(encoding="utf-8")
    for required in (
        "utterance.onstart",
        "utterance.onboundary",
        "utterance.onend",
        "_startCadence(rate)",
        "clearInterval(this.pulseTimer)",
        "this._setFace(id,true)",
        "this._setFace(id,false)",
        "setHaroArtSpeaking(id,enabled)",
        "data-speaker=\"orange\"",
        "data-speaker=\"purple\"",
        "data-speaker=\"green\"",
    ):
        assert required in source


def test_speech_settings_and_original_effects():
    """発表用の音声ピッチ・話速と電子音の設定を保持する。"""
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
    ):
        assert method in source
