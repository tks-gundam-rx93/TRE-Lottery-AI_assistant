"""音声起動・発話中のキャラクター選択・API接続の回帰テスト。"""
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_voice_controls_and_wakeword():
    """起動語・初回応答・タップ代替が引き続き利用できる。"""
    page = UI.read_text(encoding="utf-8")
    assert "おーい、ハロ" in page
    assert "haroSpeech.say('タカシ、元気か？','orange')" in page
    for element_id in ("voice-mic-btn", "voice-wake-btn", "voice-stop-btn", "voice-status", "voice-output"):
        assert f'id="{element_id}"' in page


def test_speaking_animation_only_current_agent():
    """3体分6つの発光スポットと、1体ずつの発話完了処理を確認。"""
    page = UI.read_text(encoding="utf-8")
    assert page.count('class="haro-eye-pulse ') == 6
    assert "setHaroArtSpeaking(id,enabled)" in page
    assert "utterance.onboundary" in page
    assert "this._setFace(id,false)" in page
    assert "const haroByAgent={LOGOS:'orange',CHAOS:'purple',NEMESIS:'green'};" in page


def test_speech_recognition_error_and_echo_prevention():
    page = UI.read_text(encoding="utf-8")
    for required in (
        "window.SpeechRecognition||window.webkitSpeechRecognition",
        "not-allowed", "audio-capture", "service-not-allowed",
        "pauseForSpeech()", "resumeAfterSpeech()", "this.recognition.abort()",
        "async function dispatchHaroCommand", "async function readDebateAloud",
    ):
        assert required in page


def test_prediction_api_remains_connected():
    page = UI.read_text(encoding="utf-8")
    assert "fetch('/api/predict'" in page
    assert "fetch('/api/history/upload'" in page
    assert "fetch('/api/health'" in page
