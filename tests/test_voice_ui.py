"""ハロ音声UIの公開時回帰テスト（外部マイクやTTSは要求しない）。"""

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_voice_controls_and_wakeword():
    """起動語・初回応答・タップ代替手段が存在すること。"""
    page = UI.read_text(encoding="utf-8")
    assert "おーい、ハロ" in page
    assert "haroSpeech.say('タカシ、元気か？','orange')" in page
    for element_id in ["voice-mic-btn", "voice-wake-btn", "voice-stop-btn", "voice-status", "voice-output"]:
        assert f'id="{element_id}"' in page


def test_speaking_animation_only_for_active_haro():
    """ハロごとの目・耳の動作と発話終了時のクリーンアップ。"""
    page = UI.read_text(encoding="utf-8")
    assert page.count('class="voice-eye"') == 6
    assert ".haro.speaking .ears" in page
    assert ".haro.speaking .voice-eye" in page
    assert "utterance.onboundary" in page
    assert "this._setFace(id,false)" in page


def test_speech_recognition_permission_and_echo_prevention():
    """音声認識の対応判定・権限エラー・読み上げ中の認識停止。"""
    page = UI.read_text(encoding="utf-8")
    for required in [
        "window.SpeechRecognition||window.webkitSpeechRecognition",
        "not-allowed", "audio-capture", "service-not-allowed",
        "pauseForSpeech()", "resumeAfterSpeech()", "this.recognition.abort()",
        "async function dispatchHaroCommand", "async function readDebateAloud"
    ]:
        assert required in page


def test_original_prediction_endpoint_unchanged():
    """音声の追加後も既存の予測・CSVインポート機能に接続できる構成。"""
    page = UI.read_text(encoding="utf-8")
    assert "fetch('/api/predict'" in page
    assert "fetch('/api/history/upload'" in page
    assert "fetch('/api/health'" in page
