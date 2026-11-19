"""方式1のWeb SpeechとGIF再生連動のテスト。"""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_voice_events_manage_gif_lifecycle():
    """TTS開始後にGIFを再生、読み上げ終了・停止時に閉耳へ戻す。"""
    html = SOURCE.read_text(encoding="utf-8")
    for token in (
        "utterance.onstart", "utterance.onboundary", "utterance.onend",
        "this._setFace(id,true)", "this._setFace(id,false)",
        "setHaroArtSpeaking(id,enabled)",
        "class HaroGifPlaybackController",
        "haroVisual.setSpeaker(id,enabled)",
        "gif.onerror", "gif.onload",
        "gif.removeAttribute('src')",
    ):
        assert token in html


def test_browser_voice_settings_preserved():
    html = SOURCE.read_text(encoding="utf-8")
    for ident in ("voice-pitch", "voice-rate", "voice-chirp",
                  "voice-pitch-label", "voice-rate-label"):
        assert html.count(f'id="{ident}"') == 1
    for token in (
        "armAudio(){", "_chirp(){", "restoreSettings(){",
        "preview(){", "new SpeechSynthesisUtterance",
        "tre_haro_voice_settings", "let startGuard=null;"
    ):
        assert token in html


def test_selected_agent_not_confused_with_gif_animation():
    """誰が発話中かは保持するが、GIFの3体は分離して動かせないことを明示。"""
    html = SOURCE.read_text(encoding="utf-8")
    assert "this.speaker=id" in html
    assert "stage.dataset.speaker=id" in html
    assert "3体の個別アニメーション制御が必要なら方式2" in html
    assert "3体が同時に動くGIF" in html
