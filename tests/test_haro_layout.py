"""方式1：GIF + 待機静止画の描画・状態管理の回帰テスト。"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "index.html"
ASSETS = ROOT / "web" / "assets"


def html_text():
    return PAGE.read_text(encoding="utf-8")


def test_original_8_frame_gif_is_preserved():
    """生成された原GIFを改変せずに保存し、180ms×8フレームを検証する。"""
    content = (ASSETS / "haro-speaking.gif").read_bytes()
    assert content[:6] in (b"GIF89a", b"GIF87a")
    assert int.from_bytes(content[6:8], "little") == 507
    assert int.from_bytes(content[8:10], "little") == 378
    blocks = re.findall(rb"\x21\xf9\x04.{1}(.{2})", content, re.DOTALL)
    assert len(blocks) == 8
    assert [int.from_bytes(block, "little") for block in blocks] == [18] * 8


def test_idle_image_is_webp_first_frame():
    """待機画像は同じ寸法のWebPで、発話時以外はGIFを表示しない。"""
    content = (ASSETS / "haro-idle.webp").read_bytes()
    assert content[:4] == b"RIFF"
    assert content[8:12] == b"WEBP"
    html = html_text()
    assert 'src="/assets/haro-idle.webp"' in html
    assert 'id="haro-animation"' in html
    assert 'haro-animation' in html
    assert 'hidden>' in html
    assert '<svg class="haro-vector"' not in html
    assert "class HaroGifPlaybackController" in html


def test_three_agents_and_mobile_interactive_hotspots():
    """1枚のGIF上に、オレンジ・緑・紫の独立した選択操作を重ねる。"""
    html = html_text()
    for name in ("green", "orange", "purple"):
        assert html.count(f'id="pod-{name}"') == 1
        assert f"selectHaro('{name}')" in html
    assert 'id="pod-blue"' not in html
    assert '.stage.gif-stage{height:auto}' in html
    assert '@media(max-width:560px)' in html
    assert "purple:'CHAOS'" in html


def test_animation_only_playing_when_speaking():
    """通常は静止画、音声開始時だけGIFを読み、終了時にsrcを解除する。"""
    html = html_text()
    for expected in (
        "setSpeaker(id,enabled)",
        "stage.classList.add('talking')",
        "gif.src=this.gifPath+'?play='+serial",
        "gif.removeAttribute('src')",
        "gif.hidden=true",
        "stage.classList.remove('talking','loaded','voice-accent')",
        "haroVisual.setSpeaker(id,enabled)",
        "function previewHaroMotion()",
        "},4600);",
    ):
        assert expected in html
    assert "1周1.44秒" in html
    assert "3体が同時に動くGIF" in html


def test_fast_gif_doubles_opening_speed_without_changing_frame_pixels():
    """フレーム内容は完全同一、GCEの待機時間だけを変更した高速GIF。"""
    original = (ASSETS / "haro-speaking.gif").read_bytes()
    fast = (ASSETS / "haro-speaking-fast.gif").read_bytes()
    assert len(original) == len(fast)
    assert original[:6] == fast[:6] == b"GIF89a"
    assert original[6:10] == fast[6:10]  # 解像度は507×378
    first = [m.start() for m in re.finditer(b"\\x21\\xf9\\x04", original)]
    second = [m.start() for m in re.finditer(b"\\x21\\xf9\\x04", fast)]
    assert first == second and len(first) == 8
    old_delays = [int.from_bytes(original[i + 4:i + 6], "little") for i in first]
    new_delays = [int.from_bytes(fast[i + 4:i + 6], "little") for i in second]
    assert old_delays == [18] * 8
    # 1〜4枚目:90ms / 全開5〜6枚目:200ms / 閉動作7〜8枚目:130ms
    assert new_delays == [9, 9, 9, 9, 20, 20, 13, 13]
    assert sum(new_delays) == 102  # 1周1,020ms (元は1,440ms)
    # 全バイトのうち遅延指定の16バイト以外を改変していないことを検証。
    restored = bytearray(fast)
    for i in second:
        restored[i + 4:i + 6] = original[i + 4:i + 6]
    assert bytes(restored) == original


def test_speed_selector_defaults_to_fast_and_supports_normal():
    """画面の初期値は高速。標準に戻せる制御を用意する。"""
    html = html_text()
    assert 'id="haro-speed"' in html
    assert '<option value="fast" selected>' in html
    assert '<option value="normal">' in html
    assert "this.playbackMode='fast'" in html
    assert "setPlaybackMode(value)" in html
    assert "this.playbackMode==='fast'" in html
    assert "this.gifPath+'?play='+serial" in html
