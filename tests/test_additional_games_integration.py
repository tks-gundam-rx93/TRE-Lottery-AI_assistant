"""使い捨てMySQL 8でのLOTO6・NUMBERS4履歴一括取込・再実行結合テスト。

RUN_MYSQL_INTEGRATION=1 のCI環境だけで動く。本番DBにはアクセスしない。
"""
import os

import pytest

from lottery_ai.additional_games import (
    AdditionalGameArchive, AdditionalGameRepository, Loto6Draw, Numbers4Draw,
)
from lottery_ai.mysql_repository import MySqlDrawRepository, MySqlSettings


@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="一時MySQL 8の起動されたCIジョブだけで実行",
)
def test_import_loto6_and_numbers4_as_separate_tables_and_preserve_loto7():
    mysql = MySqlDrawRepository(
        MySqlSettings(
            host="127.0.0.1", port=3306, user="tre_ci",
            password="ci_only_password", database="tre_lottery", ssl_mode="disabled"
        )
    )
    loader = AdditionalGameArchive()
    repo = AdditionalGameRepository(mysql)

    # 既存LOTO7データにはINSERTもDELETEも行わない。
    loto7_before = mysql.stats()

    loto6 = loader.load("LOTO6")
    first = repo.import_draws("LOTO6", loto6)
    assert first["inserted"] == 2156
    assert first["skipped"] == 0
    assert first["db_rows"] == 2156
    assert repo.stats("LOTO6")["missing_count"] == 0
    again = repo.import_draws("LOTO6", loto6)
    assert again["inserted"] == 0 and again["skipped"] == 2156
    assert repo.stats("LOTO6")["last_draw"] == 2156

    numbers4 = loader.load("NUMBERS4")
    first4 = repo.import_draws("NUMBERS4", numbers4)
    assert first4["inserted"] == 6436
    assert first4["skipped"] == 0
    assert first4["db_rows"] == 6436
    again4 = repo.import_draws("NUMBERS4", numbers4)
    assert again4["inserted"] == 0 and again4["skipped"] == 6436
    assert repo.stats("NUMBERS4")["missing_count"] == 0

    # 先頭ゼロを含む数字を型変換せずにDBから取得。
    conn = mysql._connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT winning_number FROM numbers4_draw_results WHERE draw_no=%s", (3,)
            )
            assert cursor.fetchone()[0] == "0097"
            cursor.execute(
                "SELECT numbers_json,bonus_number,draw_date "
                "FROM loto6_draw_results WHERE draw_no=%s", (2134,)
            )
            raw, bonus, draw_date = cursor.fetchone()
            assert raw == "[5, 9, 10, 19, 26, 35]"
            assert int(bonus) == 18
            assert draw_date is None
    finally:
        conn.close()

    # 既存回の改ざんはエラー・ロールバック。
    inconsistent = list(loto6)
    inconsistent[0] = Loto6Draw(1, (1, 8, 10, 13, 27, 30), 39)
    with pytest.raises(ValueError, match="矛盾"):
        repo.import_draws("LOTO6", inconsistent)
    assert repo.stats("LOTO6")["count"] == 2156
    assert mysql.stats() == loto7_before
