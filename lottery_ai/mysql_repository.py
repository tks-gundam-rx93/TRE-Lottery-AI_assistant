"""ローカルXAMPP/MySQL (phpMyAdmin) 用の永続化リポジトリ。

MySQLはWeb APIと同じWindows PC上で稼働させ、利用者のブラウザへDB認証情報を渡さない。
接続情報は環境変数から読み込み、GitHubにパスワードを保存しない。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import threading
import uuid
from typing import Any

from .core import Draw


@dataclass(frozen=True)
class MySqlSettings:
    """環境ごとにDB接続を切り替える。デフォルトはローカルホスト。"""

    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "tre_lottery_app"
    password: str = ""
    database: str = "tre_lottery"

    @classmethod
    def from_env(cls) -> "MySqlSettings":
        database = os.getenv("LOTTERY_DB_NAME", "tre_lottery")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", database):
            raise ValueError("LOTTERY_DB_NAMEには英数字とアンダースコアを使ってください")
        return cls(
            host=os.getenv("LOTTERY_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("LOTTERY_DB_PORT", "3306")),
            user=os.getenv("LOTTERY_DB_USER", "tre_lottery_app"),
            password=os.getenv("LOTTERY_DB_PASSWORD", ""),
            database=database,
        )


class MySqlDrawRepository:
    """既存回の値が一致しない場合は上書きせず拒否する、ロト7の永続リポジトリ。"""

    DRAW_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS draw_results (
            lottery_type VARCHAR(16) NOT NULL,
            draw_no INTEGER NOT NULL,
            draw_date VARCHAR(64) NOT NULL,
            numbers_json TEXT NOT NULL,
            bonus_json TEXT NOT NULL,
            source VARCHAR(32) NOT NULL,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lottery_type, draw_no)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    PREDICTION_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS prediction_runs (
            run_id CHAR(32) NOT NULL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lottery_type VARCHAR(16) NOT NULL,
            mode VARCHAR(32) NOT NULL,
            target_draw INTEGER NULL,
            result_json LONGTEXT NOT NULL,
            INDEX idx_prediction_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """

    def __init__(self, settings: MySqlSettings):
        self.settings = settings
        self._initialized = False
        self._lock = threading.Lock()

    def _connect(self):
        """DBへの接続はバックエンドのみで行い、資格情報を画面へ送らない。"""
        import pymysql
        return pymysql.connect(
            host=self.settings.host, port=self.settings.port,
            user=self.settings.user, password=self.settings.password,
            database=self.settings.database, charset="utf8mb4",
            connect_timeout=3, read_timeout=10, write_timeout=10,
            autocommit=False
        )

    def ensure_schema(self):
        """初回アクセスでCREATE TABLE IF NOT EXISTSを実行（DB自体は事前作成）。"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            conn = self._connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(self.DRAW_TABLE_SQL)
                    cursor.execute(self.PREDICTION_TABLE_SQL)
                conn.commit()
                self._initialized = True
            finally:
                conn.close()

    def all(self) -> list[Draw]:
        """登録済みの本数字・ボーナス数字を回号順に読み込む。"""
        self.ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT draw_no, draw_date, numbers_json, bonus_json "
                    "FROM draw_results WHERE lottery_type=%s ORDER BY draw_no",
                    ("LOTO7",)
                )
                rows = cursor.fetchall()
            return [
                Draw(int(n), str(date), tuple(json.loads(nums)), tuple(json.loads(bonus)))
                for n, date, nums, bonus in rows
            ]
        finally:
            conn.close()

    def upsert(self, draws: list[Draw], source: str = "CSV") -> int:
        """同一回はスキップ。相違のある既存回は明示エラーとして一括ロールバック。"""
        self.ensure_schema()
        conn = self._connect()
        inserted = 0
        try:
            with conn.cursor() as cursor:
                for d in draws:
                    cursor.execute(
                        "SELECT draw_date, numbers_json, bonus_json FROM draw_results "
                        "WHERE lottery_type=%s AND draw_no=%s FOR UPDATE",
                        ("LOTO7", d.draw_no)
                    )
                    prior = cursor.fetchone()
                    values = (str(d.draw_date), json.dumps(d.numbers), json.dumps(d.bonus))
                    if prior is not None:
                        if (str(prior[0]), *prior[1:]) != values:
                            raise ValueError(f"DBとCSVの第{d.draw_no}回が一致しません")
                        continue
                    cursor.execute(
                        "INSERT INTO draw_results "
                        "(lottery_type, draw_no, draw_date, numbers_json, bonus_json, source) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        ("LOTO7", d.draw_no, *values, source)
                    )
                    inserted += 1
            conn.commit()
            return inserted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_prediction(self, result: dict[str, Any]) -> str:
        """番号候補・学習スコア・3AI判定をJSON形式で保存する。"""
        self.ensure_schema()
        prediction_id = uuid.uuid4().hex
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO prediction_runs "
                    "(run_id, lottery_type, mode, target_draw, result_json) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        prediction_id, "LOTO7", result["mode"], result["target_draw"],
                        json.dumps(result, ensure_ascii=False)
                    )
                )
            conn.commit()
            return prediction_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
