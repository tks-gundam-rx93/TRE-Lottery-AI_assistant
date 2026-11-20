"""MySQL履歴・予測履歴の永続化（Renderプライベート／外部クラウドDB対応）。

APIのみがDBへ接続する。ブラウザには接続パスワードを渡さない。
遠隔接続では証明書を検証するTLSを既定とし、明示的なプライベート網だけ無効化可能。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import ssl
from urllib.parse import urlsplit, unquote
import threading
import uuid
from typing import Any

from .core import Draw


@dataclass(frozen=True)
class MySqlSettings:
    """DBホストと認証情報は環境変数にのみ保持する。

    LOTTERY_MYSQL_URL の例:
    mysql+pymysql://app_user:ENCODED_PASSWORD@db.example.com:3306/tre_lottery
    URLが未指定なら従来の LOTTERY_DB_HOST / USER 等を参照する。
    """

    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "tre_lottery_app"
    password: str = ""
    database: str = "tre_lottery"
    ssl_mode: str = "verify"
    ssl_ca: str | None = None

    @classmethod
    def from_env(cls) -> "MySqlSettings":
        url = os.getenv("LOTTERY_MYSQL_URL", "").strip()
        if url:
            parts = urlsplit(url)
            if parts.scheme not in ("mysql", "mysql+pymysql"):
                raise ValueError("LOTTERY_MYSQL_URLはmysql://形式で指定してください")
            if not parts.hostname or parts.username is None or not parts.path.strip("/"):
                raise ValueError("MySQL URLにホスト・ユーザー・DB名が必要です")
            if parts.query or parts.fragment or "/" in parts.path.strip("/"):
                raise ValueError("MySQL URLのクエリ／追加パスは使えません")
            host = parts.hostname
            port = parts.port or 3306
            user = unquote(parts.username)
            password = unquote(parts.password or "")
            database = unquote(parts.path.lstrip("/"))
        else:
            host = os.getenv("LOTTERY_DB_HOST", "127.0.0.1").strip()
            port = int(os.getenv("LOTTERY_DB_PORT", "3306"))
            user = os.getenv("LOTTERY_DB_USER", "tre_lottery_app").strip()
            password = os.getenv("LOTTERY_DB_PASSWORD", "")
            database = os.getenv("LOTTERY_DB_NAME", "tre_lottery").strip()

        if not host or not user or not 1 <= port <= 65535:
            raise ValueError("MySQLホスト・ユーザー・ポートを確認してください")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", database):
            raise ValueError("DB名には英数字とアンダースコアを使ってください")
        ssl_mode = os.getenv("LOTTERY_DB_SSL_MODE", "verify").strip().lower()
        if ssl_mode not in ("verify", "disabled"):
            raise ValueError("LOTTERY_DB_SSL_MODEはverifyまたはdisabledのみ")
        return cls(
            host=host, port=port, user=user, password=password, database=database,
            ssl_mode=ssl_mode,
            ssl_ca=os.getenv("LOTTERY_DB_SSL_CA") or None,
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
        kwargs = dict(
            host=self.settings.host, port=self.settings.port,
            user=self.settings.user, password=self.settings.password,
            database=self.settings.database, charset="utf8mb4",
            connect_timeout=5, read_timeout=15, write_timeout=15,
            autocommit=False,
        )
        if self.settings.ssl_mode == "verify":
            # クラウドDBのCA証明書とホスト名を厳密に検証。
            # Render内のプライベートMySQLだけ LOTTERY_DB_SSL_MODE=disabled を指定可能。
            kwargs["ssl"] = ssl.create_default_context(cafile=self.settings.ssl_ca)
        return pymysql.connect(**kwargs)

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

    def stats(self) -> dict[str, int | str | None]:
        """履歴の範囲と欠落回号を返す。公開APIでは接続情報を返さない。"""
        self.ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*), MIN(draw_no), MAX(draw_no) "
                    "FROM draw_results WHERE lottery_type=%s", ("LOTO7",)
                )
                count, first, last = cursor.fetchone()
                cursor.execute(
                    "SELECT draw_no, draw_date FROM draw_results "
                    "WHERE lottery_type=%s ORDER BY draw_no DESC LIMIT 1", ("LOTO7",)
                )
                latest = cursor.fetchone()
                return {
                    "count": int(count), "first_draw": int(first) if first is not None else None,
                    "last_draw": int(last) if last is not None else None,
                    "last_date": str(latest[1]) if latest else None,
                    # 途中の欠落回号は明示して点検する（初期導入では第1回からが理想）。
                    "missing_count": int(last-first+1-count) if first is not None else 0,
                }
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
