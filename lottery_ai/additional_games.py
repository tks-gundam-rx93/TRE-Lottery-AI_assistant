"""LOTO6・NUMBERS4の履歴をTiDB Cloudに永続化するサービス。

- LOTO7専用Drawを流用しない（LOTO6は6+1、NUMBERS4は順序付き4桁）。
- 添付ファイルに抽せん日が含まれないため、日付はNULLで保存する。
- ユーザー提供ファイルの検証済みgzip/CSVをSHA-256で確認してから登録する。
- 既存のLOTO7テーブルは読み書きしない。
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import csv
import gzip
import io
import json
import re
from typing import Literal

from .mysql_repository import MySqlDrawRepository


GameCode = Literal["LOTO6", "NUMBERS4"]


@dataclass(frozen=True)
class Loto6Draw:
    """1～43の本数字6個と、重複しないボーナス数字1個。"""

    draw_no: int
    numbers: tuple[int, ...]
    bonus: int

    def __post_init__(self) -> None:
        if self.draw_no < 1 or len(self.numbers) != 6:
            raise ValueError("LOTO6の回号または本数字の個数が不正です")
        if tuple(sorted(self.numbers)) != self.numbers:
            raise ValueError("LOTO6の本数字が昇順でありません")
        if (len(set(self.numbers)) != 6
                or any(not 1 <= number <= 43 for number in self.numbers)
                or not 1 <= self.bonus <= 43 or self.bonus in self.numbers):
            raise ValueError(f"第{self.draw_no}回のLOTO6数字が不正です")


@dataclass(frozen=True)
class Numbers4Draw:
    """0000～9999の文字列。先頭ゼロと数字の並び・重複を保持する。"""

    draw_no: int
    winning_number: str

    def __post_init__(self) -> None:
        if self.draw_no < 1 or not re.fullmatch(r"[0-9]{4}", self.winning_number):
            raise ValueError("NUMBERS4は正確に4桁の文字列で指定してください")


class AdditionalGameArchive:
    """公開データの変更や欠落を検知する、イミュータブルな配布CSVリーダー。"""

    ROOT = Path(__file__).resolve().parents[1] / "data"
    SOURCES = {
        "LOTO6": {
            "file": "loto6_draws_001_2156.csv.gz",
            "gzip_sha256": "cf882f64856af3de4b8676245fd2c599fcf5e75bd91c5a8f1a65d7adb9775ccd",
            "csv_sha256": "0c2a8d542b93b4aa7d02fe1012bf90d22e6dedc472429c156943308ae2ab4733",
            "count": 2156,
            "columns": ["draw_no", "n1", "n2", "n3", "n4", "n5", "n6", "bonus"],
        },
        "NUMBERS4": {
            "file": "numbers4_draws_001_6436.csv.gz",
            "gzip_sha256": "04b816f2458ed1450102dacdc372e8864ef161eeae6457e6e322f2d3bc1dca90",
            "csv_sha256": "3e275ae052c091cee2848f7e07ddde25a5b36c25f8493cfb9972f1b89b6ae202",
            "count": 6436,
            "columns": ["draw_no", "winning_number"],
        },
    }

    def load(self, game: GameCode) -> list[Loto6Draw] | list[Numbers4Draw]:
        if game not in self.SOURCES:
            raise ValueError("未対応の宝くじ種別です")
        config = self.SOURCES[game]
        compressed = (self.ROOT / config["file"]).read_bytes()
        if sha256(compressed).hexdigest() != config["gzip_sha256"]:
            raise ValueError(f"{game} gzipファイルの整合性検証に失敗しました")
        raw = gzip.decompress(compressed)
        if sha256(raw).hexdigest() != config["csv_sha256"]:
            raise ValueError(f"{game} CSVの整合性検証に失敗しました")
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames != config["columns"]:
            raise ValueError(f"{game} CSVヘッダーが仕様と一致しません")
        items = []
        for expected, row in enumerate(reader, start=1):
            try:
                if int(row["draw_no"]) != expected:
                    raise ValueError("連続回号に欠落・重複があります")
                if game == "LOTO6":
                    numbers = tuple(int(row[f"n{i}"]) for i in range(1, 7))
                    item = Loto6Draw(expected, numbers, int(row["bonus"]))
                else:
                    item = Numbers4Draw(expected, row["winning_number"])
                items.append(item)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{game} CSVの第{expected}回が不正です") from exc
        if len(items) != config["count"]:
            raise ValueError(f"{game} CSVの登録件数が不正です")
        if game == "LOTO6":
            if items[2133] != Loto6Draw(2134, (5, 9, 10, 19, 26, 35), 18):
                raise ValueError("LOTO6第2134回の確認済み訂正と一致しません")
        else:
            if items[0].winning_number != "1149" or items[-1].winning_number != "8399":
                raise ValueError("NUMBERS4の始終回と一致しません")
        return items


class AdditionalGameRepository:
    """ゲーム別テーブルへの原子的な初回登録と重複防止を担当する。"""

    TABLES = {
        "LOTO6": "loto6_draw_results",
        "NUMBERS4": "numbers4_draw_results",
    }
    CREATE_LOTO6 = """CREATE TABLE IF NOT EXISTS loto6_draw_results (
        draw_no INT NOT NULL PRIMARY KEY,
        draw_date DATE NULL,
        numbers_json TEXT NOT NULL,
        bonus_number INT NOT NULL,
        source VARCHAR(40) NOT NULL,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
    CREATE_NUMBERS4 = """CREATE TABLE IF NOT EXISTS numbers4_draw_results (
        draw_no INT NOT NULL PRIMARY KEY,
        draw_date DATE NULL,
        winning_number CHAR(4) NOT NULL,
        source VARCHAR(40) NOT NULL,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""

    def __init__(self, mysql: MySqlDrawRepository):
        self.mysql = mysql

    @classmethod
    def validate_game(cls, game: str) -> GameCode:
        if game not in cls.TABLES:
            raise ValueError("LOTO6またはNUMBERS4を指定してください")
        return game  # type: ignore[return-value]

    def _ensure_schema(self) -> None:
        """新規2テーブルを作成。LOTO7テーブルには触れない。"""
        conn = self.mysql._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(self.CREATE_LOTO6)
                cursor.execute(self.CREATE_NUMBERS4)
            conn.commit()
        finally:
            conn.close()

    def stats(self, game: str) -> dict[str, int | str | None]:
        self.validate_game(game)
        self._ensure_schema()
        conn = self.mysql._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*), MIN(draw_no), MAX(draw_no) FROM {self.TABLES[game]}"
                )
                count, first, last = cursor.fetchone()
            return {
                "game": game, "count": int(count),
                "first_draw": int(first) if first is not None else None,
                "last_draw": int(last) if last is not None else None,
                "missing_count": int(last - first + 1 - count) if first is not None else 0,
                "dates_available": False,
            }
        finally:
            conn.close()

    def import_draws(
        self, game: GameCode, draws: list[Loto6Draw] | list[Numbers4Draw],
        source: str = "USER_CSV_VERIFIED",
    ) -> dict[str, int | str | None]:
        self.validate_game(game)
        if not draws:
            raise ValueError("取込対象がありません")
        if len({d.draw_no for d in draws}) != len(draws):
            raise ValueError("取込対象CSVに回号の重複があります")
        # 厳密にデータ型と範囲をチェックしてからDBに接続する。
        expected_type = Loto6Draw if game == "LOTO6" else Numbers4Draw
        if any(not isinstance(d, expected_type) for d in draws):
            raise ValueError("抽せんゲームのデータ形式が一致しません")
        self._ensure_schema()
        conn = self.mysql._connect()
        try:
            with conn.cursor() as cursor:
                if game == "LOTO6":
                    cursor.execute(
                        "SELECT draw_no,numbers_json,bonus_number FROM "
                        "loto6_draw_results FOR UPDATE"
                    )
                    existing = {
                        int(no): (tuple(json.loads(numbers)), int(bonus))
                        for no, numbers, bonus in cursor.fetchall()
                    }
                    pending = []
                    for draw in draws:
                        value = (draw.numbers, draw.bonus)
                        if draw.draw_no in existing:
                            if existing[draw.draw_no] != value:
                                raise ValueError(f"LOTO6第{draw.draw_no}回がDBと矛盾しています")
                        else:
                            pending.append((
                                draw.draw_no, None, json.dumps(draw.numbers),
                                draw.bonus, source,
                            ))
                    if pending:
                        cursor.executemany(
                            "INSERT INTO loto6_draw_results "
                            "(draw_no,draw_date,numbers_json,bonus_number,source) "
                            "VALUES (%s,%s,%s,%s,%s)", pending
                        )
                else:
                    cursor.execute(
                        "SELECT draw_no,winning_number FROM "
                        "numbers4_draw_results FOR UPDATE"
                    )
                    existing = {
                        int(no): str(number) for no, number in cursor.fetchall()
                    }
                    pending = []
                    for draw in draws:
                        if draw.draw_no in existing:
                            if existing[draw.draw_no] != draw.winning_number:
                                raise ValueError(
                                    f"NUMBERS4第{draw.draw_no}回がDBと矛盾しています"
                                )
                        else:
                            pending.append((draw.draw_no, None, draw.winning_number, source))
                    if pending:
                        cursor.executemany(
                            "INSERT INTO numbers4_draw_results "
                            "(draw_no,draw_date,winning_number,source) "
                            "VALUES (%s,%s,%s,%s)", pending
                        )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        summary = self.stats(game)
        return {
            "game": game,
            "rows_in_file": len(draws),
            "inserted": len(pending),
            "skipped": len(draws) - len(pending),
            "db_rows": summary["count"],
            "last_draw": summary["last_draw"],
        }
