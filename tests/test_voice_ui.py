"""音声制御・ハロの独立動作・APIとの互換性テスト。"""
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_voice_controls_and_wakeword():
    page = UI.read_text(encoding="utf-8")
    assert "おーい、ハロ" in page
    assert "haroSpeech.say('タカシ、元気か？','orange')" in page
    for ident in ("voice-mic-btn", "voice-wake-btn", "voice-stop-btn", "voice-status", "voice-output"):
        assert f'id="{ident}"' in page


def test_speaking_one_haro_only():
    page = UI.read_text(encoding="utf-8")
    assert page.count('class="eye-pair"') == 3
    assert ".haro-unit.speaking .eye-pair" in page
    assert ".haro-unit.speaking .hatch-left" in page
    assert ".haro-unit.speaking .hatch-right" in page
    assert "haroVisual.setSpeaker(id,enabled)" in page
    assert "this._setFace(id,false)" in page
    assert "const haroByAgent={LOGOS:'orange',CHAOS:'purple',NEMESIS:'green'};" in page


def test_browser_recognition_and_echo_prevention():
    page = UI.read_text(encoding="utf-8")
    for expected in ("window.SpeechRecognition||window.webkitSpeechRecognition",
                     "not-allowed", "audio-capture", "service-not-allowed",
                     "pauseForSpeech()", "resumeAfterSpeech()", "this.recognition.abort()",
                     "async function dispatchHaroCommand", "async function readDebateAloud"):
        assert expected in page


def test_original_api_endpoints():
    page = UI.read_text(encoding="utf-8")
    assert "fetch('/api/predict'" in page
    assert "fetch('/api/history/upload'" in page
    assert "fetch('/api/health'" in page
