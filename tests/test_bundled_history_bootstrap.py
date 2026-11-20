"""ユーザー提供LOTO7の第1～703回CSVとTiDB初期取込の回帰テスト。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lottery_ai.bootstrap_history import Loto7HistoryBootstrap
from lottery_ai.core import Draw


class FakeMySql:
    """データ競合・重複抑止の動作を実DBを使わず検証。"""

    def __init__(self):
        self.rows: dict[int, Draw] = {}
        self.calls = 0

    def all(self):
        return sorted(self.rows.values(), key=lambda draw: draw.draw_no)

    def upsert(self, draws, source="CSV"):
        return self.upsert_many(draws, source)

    def upsert_many(self, draws, source="CSV"):
        self.calls += 1
        # all-or-nothing: 最初に一括検証する。
        for draw in draws:
            old = self.rows.get(draw.draw_no)
            if old is not None and old != draw:
                raise ValueError(f"DBとCSVの第{draw.draw_no}回が一致しません")
        pending = [d for d in draws if d.draw_no not in self.rows]
        for draw in pending:
            self.rows[draw.draw_no] = draw
        return len(pending)

    def stats(self):
        return {"count": len(self.rows)}


def test_bundled_history_validation_and_known_483_date():
    verified = Loto7HistoryBootstrap(FakeMySql()).validate()
    assert verified["count"] == 703
    assert verified["first_draw"] == 1
    assert verified["last_draw"] == 703
    assert verified["sha256"] == Loto7HistoryBootstrap.SHA256


def test_history_bulk_import_is_repeatable_without_duplicate():
    repo = FakeMySql()
    boot = Loto7HistoryBootstrap(repo)
    first = boot.run()
    assert first["csv_rows"] == 703
    assert first["inserted"] == 703
    assert first["db_rows"] == 703
    assert len(repo.rows) == 703
    assert repo.rows[483].draw_date == "2022-08-12"
    assert repo.rows[703].draw_date == "2026-11-13"
    again = boot.run()
    assert again["inserted"] == 0
    assert again["skipped"] == 703
    assert again["db_rows"] == 703
    assert repo.calls == 2


def test_history_import_conflict_leaves_database_untouched():
    repo = FakeMySql()
    repo.rows[483] = Draw(483, "2022-08-13", (2, 11, 20, 23, 25, 36, 37), (29, 34))
    snapshot = dict(repo.rows)
    with pytest.raises(ValueError, match="矛盾"):
        Loto7HistoryBootstrap(repo).run()
    assert repo.rows == snapshot


def test_truncated_history_never_overwrites_db(tmp_path: Path):
    invalid = tmp_path / "loto7.csv"
    invalid.write_text(
        "draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7,b1,b2\n"
        "1,2013-04-05,7,10,12,17,23,28,34,3,15\n", encoding="utf-8"
    )
    repo = FakeMySql()
    with pytest.raises(ValueError, match="履歴件数"):
        Loto7HistoryBootstrap(repo, invalid).run()
    assert repo.calls == 0


def test_bootstrap_disabled_when_environment_variable_is_missing(monkeypatch):
    from app import import_verified_loto7_history_on_startup, service
    repo = FakeMySql()
    monkeypatch.setattr(service, "mysql", repo)
    monkeypatch.delenv("LOTTERY_BOOTSTRAP_CSV", raising=False)
    import_verified_loto7_history_on_startup()
    assert repo.calls == 0
