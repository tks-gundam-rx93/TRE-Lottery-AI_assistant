"""クラウドMySQL URL・TLS・LOTO7履歴一括/増分取込の独立テスト。

外部DBの秘密情報をCIに置かず、リポジトリの振る舞いを検証する。
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from lottery_ai.cloud_import import Loto7HistoryImporter
from lottery_ai.core import Draw
from lottery_ai.mysql_repository import MySqlSettings, MySqlDrawRepository


def test_cloud_mysql_url_decodes_password_and_enables_tls(monkeypatch):
    monkeypatch.setenv(
        "LOTTERY_MYSQL_URL",
        "mysql+pymysql://lottery_user:p%40ss%23word@mysql.example.org:3307/tre_lottery"
    )
    monkeypatch.delenv("LOTTERY_DB_SSL_MODE", raising=False)
    cfg = MySqlSettings.from_env()
    assert cfg.host == "mysql.example.org"
    assert cfg.port == 3307
    assert cfg.user == "lottery_user"
    assert cfg.password == "p@ss#word"
    assert cfg.database == "tre_lottery"
    assert cfg.ssl_mode == "verify"


def test_reject_unsupported_database_url_and_ssl_mode(monkeypatch):
    monkeypatch.setenv("LOTTERY_MYSQL_URL", "postgresql://user:pw@host/tre_lottery")
    with pytest.raises(ValueError, match="mysql"):
        MySqlSettings.from_env()
    monkeypatch.delenv("LOTTERY_MYSQL_URL", raising=False)
    monkeypatch.setenv("LOTTERY_DB_SSL_MODE", "anything")
    with pytest.raises(ValueError, match="verify"):
        MySqlSettings.from_env()


def test_private_mysql_must_explicitly_choose_plain_connection(monkeypatch):
    monkeypatch.setenv("LOTTERY_MYSQL_URL", "mysql://lottery:secret@mysql-private:3306/tre_lottery")
    monkeypatch.setenv("LOTTERY_DB_SSL_MODE", "disabled")
    cfg = MySqlSettings.from_env()
    assert cfg.host == "mysql-private"
    assert cfg.ssl_mode == "disabled"


def test_mysql_stats_sql_uses_parameterized_lottery_name():
    # SQLインジェクション対策としてドメイン名は決め打ちでパラメータとして渡す。
    assert "draw_no" in MySqlDrawRepository.DRAW_TABLE_SQL
    assert "PRIMARY KEY (lottery_type, draw_no)" in MySqlDrawRepository.DRAW_TABLE_SQL


class FakeDrawRepo:
    def __init__(self, draws=None):
        self.draws = list(draws or [])

    def all(self):
        return sorted(self.draws, key=lambda d: d.draw_no)

    def upsert(self, draws, source="CSV_MANUAL"):
        existing = {d.draw_no: d for d in self.draws}
        for item in draws:
            if item.draw_no in existing and existing[item.draw_no] != item:
                raise ValueError("conflict")
            if item.draw_no not in existing:
                self.draws.append(item)
        return len([d for d in draws if d.draw_no not in existing])

    def stats(self):
        return {"count": len(self.draws)}


def test_history_import_plan_and_idempotence(tmp_path):
    output = tmp_path / "loto7.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["draw_no","draw_date", *[f"n{i}" for i in range(1,8)], "b1", "b2"])
        writer.writerow([1, "2013/4/5", 1, 2, 3, 4, 5, 6, 7, 8, 9])
        writer.writerow([2, "2013年4月12日", 11, 12, 13, 14, 15, 16, 17, 18, 19])
    repo = FakeDrawRepo()
    importer = Loto7HistoryImporter(repo)
    dry = importer.import_csv(output, dry_run=True)
    assert dry["new_rows"] == 2
    assert dry["inserted"] == 0
    assert dry["db_rows"] == 0
    first = importer.import_csv(output)
    assert first["inserted"] == 2
    assert first["db_rows"] == 2
    assert repo.draws[0].draw_date == "2013-04-05"
    second = importer.import_csv(output)
    assert second["new_rows"] == 0
    assert second["skipped"] == 2
    assert second["inserted"] == 0


def test_history_import_rejects_conflict_without_writing(tmp_path):
    output = tmp_path / "conflict.csv"
    output.write_text(
        "draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7\n"
        "1,2013-04-05,11,12,13,14,15,16,17\n",
        encoding="utf-8"
    )
    stored = Draw(1, "2013-04-05", (1,2,3,4,5,6,7))
    repo = FakeDrawRepo([stored])
    with pytest.raises(ValueError, match="矛盾"):
        Loto7HistoryImporter(repo).import_csv(output)
    assert repo.draws == [stored]


def test_history_import_rejects_synthetic_or_future_date(tmp_path):
    filename = tmp_path / "bad.csv"
    for bad in ("SYNTHETIC-1", "2099-01-01", "2013-02-30"):
        filename.write_text(
            "draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7\n"
            f"1,{bad},1,2,3,4,5,6,7\n",
            encoding="utf-8"
        )
        with pytest.raises(ValueError):
            Loto7HistoryImporter(FakeDrawRepo()).load_and_validate(filename)


def test_no_cloud_secrets_committed():
    script = Path("lottery_ai/mysql_repository.py").read_text(encoding="utf-8")
    assert "LOTTERY_MYSQL_URL" in script
    assert "LOTTERY_DB_SSL_MODE" in script
    assert "ssl.create_default_context" in script
    assert "YOUR_PASSWORD" not in script
