"""承認済みハロ画像を使ったPC・スマホ共通UIの回帰テスト。"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "index.html"
ASSET_DIR = ROOT / "web" / "assets"


def test_approved_artwork_is_in_repository():
    """画像は外部URLではなく、ユーザー承認済みのアセットをリポジトリで配信する。"""
    for name in ("haro-approved.webp", "haro-open.webp", "haro-closed-stage.webp"):
        path = ASSET_DIR / name
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        assert 5_000 < len(data) < 400_000


def test_three_visible_units_and_purple_replaces_blue():
    """青は使わず、緑・橙・紫のヒット領域を用意する。"""
    html = PAGE.read_text(encoding="utf-8")
    for color in ("green", "orange", "purple"):
        assert html.count(f'id="pod-{color}"') == 1
        assert f"selectHaro('{color}')" in html
    assert 'id="pod-blue"' not in html
    assert "purple:'CHAOS'" in html
    assert "サブ・パープル、同期完了" in html


def test_reference_layout_and_ear_state_controls():
    """開耳画像と閉耳画像を滑らかに切り替え、音声中は開状態を優先する。"""
    html = PAGE.read_text(encoding="utf-8")
    for expected in (
        'class="haro-art-stage ears-open"',
        'src="/assets/haro-approved.webp"',
        'src="/assets/haro-closed-stage.webp"',
        'id="haro-ear-toggle"',
        "function updateHaroEars()",
        "function toggleHaroEars()",
        "function setHaroArtSpeaking(id,enabled)",
        ".haro-art-stage.ears-open .haro-art-closed",
        "aspect-ratio:1448/1086",
        "@media(max-width:500px)",
    ):
        assert expected in html
    assert "haroEarPreviewOpen || !!stage.dataset.speaker" in html


def test_speech_glows_only_current_speaker():
    """発話中の選択ハロに対応する2つの目だけ発光する。"""
    html = PAGE.read_text(encoding="utf-8")
    for color in ("green", "orange", "purple"):
        assert len(re.findall(rf'<i class="haro-eye-pulse {color}"', html)) == 2
        assert f'data-speaker="{color}"' in html
    assert "setHaroArtSpeaking(id,enabled);" in html
    assert "class HaroSpeechController" in html
    assert "class HaroVoiceAssistant" in html
    assert "haroSpeech.say('タカシ、元気か？','orange')" in html
