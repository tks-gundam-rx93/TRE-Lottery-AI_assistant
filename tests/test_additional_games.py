"""LOTO6 / NUMBERS4の配布CSV・データ型・初回取込制御の回帰テスト。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lottery_ai.additional_games import (
    AdditionalGameArchive, AdditionalGameRepository, Loto6Draw, Numbers4Draw,
)


def test_loto6_historical_bundle_and_corrected_draw():
    loader = AdditionalGameArchive()
    rows = loader.load("LOTO6")
    assert len(rows) == 2156
    assert rows[0] == Loto6Draw(1, (2, 8, 10, 13, 27, 30), 39)
    # 元CSVの29は公表結果で19と確認できたため、5,9,10,19,26,35へ訂正。
    assert rows[2133] == Loto6Draw(2134, (5, 9, 10, 19, 26, 35), 18)
    assert rows[-1] == Loto6Draw(2156, (1, 5, 23, 26, 35, 42), 8)
    assert [r.draw_no for r in rows] == list(range(1, 2157))
    assert all(len(r.numbers) == 6 and r.bonus not in r.numbers for r in rows)


def test_numbers4_bundle_preserves_4digit_order_and_leading_zeros():
    rows = AdditionalGameArchive().load("NUMBERS4")
    assert len(rows) == 6436
    assert rows[0] == Numbers4Draw(1, "1149")
    assert rows[2] == Numbers4Draw(3, "0097")
    assert rows[-1] == Numbers4Draw(6436, "8399")
    assert sum(r.winning_number.startswith("0") for r in rows) == 652
    assert [r.draw_no for r in rows] == list(range(1, 6437))


@pytest.mark.parametrize("bad", ["123", "12345", "0.123", "123X", "１２３４"])
def test_numbers4_rejects_non_ascii_four_digit_codes(bad):
    with pytest.raises(ValueError):
        Numbers4Draw(1, bad)


@pytest.mark.parametrize("bad", [
    (1, 2, 3, 4, 5, 5),
    (0, 2, 3, 4, 5, 6),
    (1, 2, 3, 4, 5, 44),
    (1, 3, 2, 4, 5, 6),
])
def test_loto6_rejects_out_of_range_duplicate_or_unsorted(bad):
    with pytest.raises(ValueError):
        Loto6Draw(1, bad, 7)


def test_missing_or_tampered_archive_fails_before_database_write(tmp_path, monkeypatch):
    monkeypatch.setattr(AdditionalGameArchive, "ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        AdditionalGameArchive().load("LOTO6")
    (tmp_path / "loto6_draws_001_2156.csv.gz").write_bytes(b"invalid gzip")
    with pytest.raises(ValueError, match="整合性"):
        AdditionalGameArchive().load("LOTO6")


def test_game_whitelist_blocks_table_name_injection():
    with pytest.raises(ValueError):
        AdditionalGameRepository.validate_game("LOTO6;DROP TABLE draw_results")
    assert AdditionalGameRepository.validate_game("LOTO6") == "LOTO6"
    assert AdditionalGameRepository.validate_game("NUMBERS4") == "NUMBERS4"


def test_bundled_data_does_not_alter_original_loto7_history():
    # LOTO7の公開済みテーブル名と、新2テーブルを厳密に分離。
    assert AdditionalGameRepository.TABLES == {
        "LOTO6": "loto6_draw_results",
        "NUMBERS4": "numbers4_draw_results",
    }
    source = Path("lottery_ai/additional_games.py").read_text(encoding="utf-8")
    assert "INSERT INTO draw_results" not in source
    assert "DELETE FROM" not in source


def test_extra_bootstrap_never_runs_without_opt_in(monkeypatch):
    from app import import_additional_game_history_on_startup, service
    monkeypatch.setenv("LOTTERY_BOOTSTRAP_ADDITIONAL_GAMES", "0")
    def fail_if_used(*args, **kwargs):
        raise AssertionError("bootstrapping must remain disabled")
    monkeypatch.setattr(AdditionalGameArchive, "load", fail_if_used)
    import_additional_game_history_on_startup()


def test_api_reports_in_memory_state_when_no_cloud_db(monkeypatch):
    from fastapi.testclient import TestClient
    from app import app, service
    monkeypatch.setattr(service, "mysql", None)
    client = TestClient(app)
    for game in ("LOTO6", "NUMBERS4"):
        resp = client.get("/api/history/status/" + game)
        assert resp.status_code == 200
        data = resp.json()
        assert data["persistent"] is False
        assert data["draw_count"] == 0
    assert client.get("/api/history/status/UNKNOWN").status_code == 404
