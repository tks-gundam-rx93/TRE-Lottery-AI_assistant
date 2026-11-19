"""ハロ3体のSVGパーツ・レスポンシブ配置・音声同期に関する回帰テスト。"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "index.html"


def page():
    return HTML.read_text(encoding="utf-8")


def unit_svg(source, color):
    match = re.search(
        rf'<button type="button" class="haro-unit haro-{color}(?: selected)?" '
        rf'id="pod-{color}"[\s\S]*?(<svg class="haro-vector"[\s\S]*?</svg>)',
        source,
    )
    assert match, f"{color} unit missing"
    return match.group(1)


def test_no_images_are_used_for_characters():
    """写真や画像をそのまま表示せず、独立したSVG要素から構成する。"""
    html = page()
    assert "<img " not in html
    assert "haro-approved.webp" not in html
    assert "haro-closed-stage.webp" not in html
    assert html.count('<svg class="haro-vector"') == 3
    assert "class HaroVectorMotionController" in html


def test_three_units_have_identical_mechanics_and_separate_color():
    """球体・閉耳外板・ヒンジ・耳内機構・目・台座の形状を3体で共通化。"""
    html = page()
    for color in ("green", "orange", "purple"):
        svg = unit_svg(html, color)
        assert 'viewBox="0 0 320 330"' in svg
        assert 'class="haro-shell"' in svg
        assert 'class="ear-cavity"' in svg
        assert 'class="hatch hatch-left"' in svg
        assert 'class="hatch hatch-right"' in svg
        assert 'class="hatch-leaf"' in svg
        assert 'class="eye-pair"' in svg
        assert 'class="eye"' in svg
        assert 'class="ear-mirror"' in svg
    assert 'id="pod-blue"' not in html
    assert "purple:'CHAOS'" in html
    assert "サブ・パープル、同期完了" in html


def test_center_front_perspective_and_responsive_design():
    html = page()
    assert "#pod-green{left:3%;bottom:2%;z-index:1}" in html
    assert "#pod-purple{right:3%;bottom:2%;z-index:2}" in html
    assert "#pod-orange{left:50%;--haro-x:-50%;bottom:-1%;width:44%;z-index:3}" in html
    assert ".haro-unit{position:absolute" in html
    assert "@media(max-width:560px)" in html
    assert ".haro-arena{height:clamp(236px,68vw,335px)" in html


def test_speaking_drives_real_hinge_rotation_instead_of_image_fading():
    html = page()
    for required in (
        "@keyframes haro-ear-hinge-left",
        "@keyframes haro-ear-hinge-right",
        "transform-origin:96px 87px",
        "transform:rotate(105deg)",
        "transform:rotate(103deg)",
        ".haro-unit.speaking .hatch-left",
        ".haro-unit.speaking .hatch-right",
        ".haro-unit.speaking .eye-pair",
        "haroVisual.setSpeaker(id,enabled)",
        "const current=stage.dataset.speaker||''",
        "IDLE / 耳 CLOSED",
    ):
        assert required in html
    assert "haroEarPreviewOpen" not in html
    assert "haro-art-closed" not in html


def test_gif_reference_visual_geometry_and_mechanics():
    """8フレームGIFに沿った開度・閉状態・装甲表現を検証する。"""
    html = page()
    for color in ("green", "orange", "purple"):
        svg = unit_svg(html, color)
        for part in ("haro-shadow-area", "ear-drive-coil", "hatch-under", "hatch-face",
                     "face-seam", "haro-shell", "ear-cavity", "haro-vector"):
            assert part in svg, (color, part)
        assert "radialGradient" in svg
        assert "linearGradient" in svg
        assert svg.count('class="ear-drive-coil"') == 2
        assert svg.count('class="hatch-under"') == 2
        assert svg.count('class="hatch-face"') == 2
    for phase in ("12.5%", "25%", "37.5%", "50%,62.5%", "75%", "87.5%"):
        assert phase in html
    assert "1.44s ease-in-out infinite" in html
    assert 'class="ear-cavity"' in html
    assert 'transform="translate(320 0) scale(-1 1)"' in html


def test_idle_eyes_dim_and_active_eyes_glow():
    """動いていない個体は暗い目、話す個体だけ明るく発光する。"""
    html = page()
    assert ".haro-unit.haro-green .eye,.haro-unit.haro-orange .eye{fill:#722433}" in html
    assert ".haro-unit.haro-purple .eye{fill:#55172b}" in html
    assert ".haro-unit.haro-purple.speaking .eye{fill:#ff283c}" in html
    assert ".haro-unit.haro-green.speaking .eye,.haro-unit.haro-orange.speaking .eye{fill:#ffe4ff}" in html
