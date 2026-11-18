"""PC・スマートフォン共通のハロ3体レイアウトに関する回帰テスト。"""

from pathlib import Path
import re

PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"


def _content():
    return PAGE.read_text(encoding="utf-8")


def _haro_svg(html: str, color: str) -> str:
    """指定されたハロのインラインSVGを取得する。"""
    m = re.search(
        rf'<button class="haro(?: selected)?" id="pod-{color}"[^>]*>\s*(<svg[\s\S]*?</svg>)',
        html,
    )
    assert m, f"{color}のSVGが存在しません"
    return m.group(1)


def test_three_haro_svg_have_identical_geometry():
    """3機の頭部・目・耳・viewBoxの形状を完全に統一する。"""
    html = _content()
    for color in ("green", "blue", "orange"):
        svg = _haro_svg(html, color)
        assert 'viewBox="0 0 240 280"' in svg
        assert '<circle class="haro-head" cx="120" cy="144" r="96"' in svg
        assert svg.count('class="voice-eye"') == 2
        assert svg.count('class="ears"') == 1
        for part in (
            'cx="98" cy="142" rx="7" ry="12"',
            'cx="142" cy="142" rx="7" ry="12"',
            'cx="46" cy="115" rx="31" ry="45"',
            'cx="194" cy="115" rx="31" ry="45"',
            'class="ear-hatch ear-hatch-left"',
            'class="ear-hatch ear-hatch-right"',
            'class="haro-head-assembly"',
            'class="ear-interior ear-interior-left"',
            'class="ear-interior ear-interior-right"',
        ):
            assert part in svg


def test_all_haro_share_one_css_size_rule():
    """別々の幅・高さを指定せず、親幅に対して共通サイズを使用する。"""
    html = _content()
    common = re.search(r"\.haro\{([^}]+)\}", html)
    assert common
    assert "width:39%" in common.group(1)
    assert "height:auto" in common.group(1)
    assert "aspect-ratio:6/7" in common.group(1)
    for color in ("green", "blue", "orange"):
        css = re.search(rf"#pod-{color}\{{([^}}]+)\}}", html)
        assert css
        assert not re.search(r"(?<!-)\b(?:width|height)\s*:", css.group(1))


def test_orange_is_center_foreground_and_mobile_is_responsive():
    """左右の背面ユニットと中央前面ユニットの重なりを維持する。"""
    html = _content()
    for color, z in (("green", 1), ("blue", 2), ("orange", 3)):
        rule = re.search(rf"#pod-{color}\{{([^}}]+)\}}", html)
        assert rule and f"z-index:{z}" in rule.group(1)
    assert "#pod-orange{left:50%" in html
    assert "--haro-shift-x:-50%" in html
    assert "translateX(var(--haro-shift-x))" in html
    assert "@media(max-width:500px)" in html
    assert "height:clamp(200px,62vw,260px)" in html


def test_speech_eye_and_ear_animation_preserved():
    """音声連動のclassと発話コントローラはそのまま使える。"""
    html = _content()
    assert ".haro.speaking .voice-eye" in html
    assert ".haro.speaking .ears" in html
    assert "class HaroVoiceAssistant" in html
    assert "class HaroSpeechController" in html
    assert html.count('class="voice-eye"') == 6
    assert "haroSpeech.say('タカシ、元気か？','orange')" in html
