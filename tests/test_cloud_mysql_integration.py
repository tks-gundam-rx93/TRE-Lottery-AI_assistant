"""MySQL 8コンテナを使う結合テスト（GitHub Actionsのみ実行）。

このテストは毎回使い捨てのMySQLを使う。本番DBにはアクセスしない。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from lottery_ai.core import Draw
from lottery_ai.cloud_import import Loto7HistoryImporter
from lottery_ai.mysql_repository import MySqlSettings, MySqlDrawRepository


@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="一時的なCI用MySQLサービスがある時のみ実行する"
)
def test_real_mysql_create_insert_duplicate_conflict_and_prediction(tmp_path):
    settings = MySqlSettings(
        host="127.0.0.1", port=3306, user="tre_ci",
        password="ci_only_password", database="tre_lottery",
        ssl_mode="disabled"  # GitHub Actionsの同一runner内の一時DB
    )
    repo = MySqlDrawRepository(settings)
    original = Draw(1, "2013-04-05", (1, 2, 3, 4, 5, 6, 7), (8, 9))
    followup = Draw(2, "2013-04-12", (4, 8, 13, 15, 19, 25, 32), (1, 2))
    assert repo.upsert([original, followup], source="CI") == 2
    assert repo.upsert([original], source="CI") == 0
    assert repo.all() == [original, followup]
    stats = repo.stats()
    assert stats["count"] == 2
    assert stats["first_draw"] == 1
    assert stats["last_draw"] == 2
    assert stats["missing_count"] == 0

    conflicting = Draw(2, "2013-04-12", (3, 8, 13, 15, 19, 25, 32), (1, 2))
    with pytest.raises(ValueError, match="一致しません"):
        repo.upsert([conflicting], source="CI_CONFLICT")
    assert repo.all() == [original, followup]

    # クラウド取込サービスで、DBに未登録の第3回だけ追加できること。
    csvfile = tmp_path / "draw_3.csv"
    csvfile.write_text(
        "draw_no,draw_date,n1,n2,n3,n4,n5,n6,n7,b1,b2\n"
        "3,2013/4/19,3,5,9,12,16,20,37,1,2\n", encoding="utf-8"
    )
    batch = Loto7HistoryImporter(repo).import_csv(csvfile)
    assert batch["inserted"] == 1
    assert batch["db_rows"] == 3
    assert repo.stats()["last_draw"] == 3

    run = {
        "mode": "MYSQL", "target_draw": 4,
        "candidates": [{"numbers": [1,2,3,4,5,6,7]}],
        "debate": {"first_round": [], "second_round": []},
    }
    prediction_id = repo.save_prediction(run)
    assert len(prediction_id) == 32
    assert uuid.UUID(hex=prediction_id)
