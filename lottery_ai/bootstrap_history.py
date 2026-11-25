"""検証済みバンドルCSVを起動時にTiDB Cloudへ初回登録する。

ユーザー提供ロト7履歴の出典・訂正は
docs/loto7_history_import_001_703.md に記録している。
ファイルの内容・回号が変わった場合は自動取込を拒否する。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .cloud_import import Loto7HistoryImporter
from .mysql_repository import MySqlDrawRepository


class Loto7HistoryBootstrap:
    """ローカルで検証したデータセットを、DBへ冪等・原子的に投入する。"""

    FILE = Path(__file__).resolve().parents[1] / "data" / "loto7_history_001_703.csv"
    SHA256 = "ab1530b24af2c965a9908fe7a2862b87a23b01b79a2d7746e8c486a7da7a79db"
    EXPECTED_COUNT = 703

    def __init__(self, repo: MySqlDrawRepository, source: Path | None = None):
        self.repo = repo
        self.source = source or self.FILE

    def validate(self) -> dict[str, Any]:
        """SHA-256・全件の日付・回号連続性を事前に検査する。"""
        raw = self.source.read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        if self.source == self.FILE and actual_hash != self.SHA256:
            raise ValueError("バンドルCSVのSHA-256が登録済みのマニフェストと一致しません")
        draws = Loto7HistoryImporter(self.repo).load_and_validate(self.source)
        if len(draws) != self.EXPECTED_COUNT:
            raise ValueError(f"履歴件数が不正です: {len(draws)}")
        if [d.draw_no for d in draws] != list(range(1, self.EXPECTED_COUNT + 1)):
            raise ValueError("第1回～703回の履歴に欠落・重複があります")
        if (draws[0].draw_date, draws[-1].draw_date) != (
            "2013-04-05", "2026-11-13"
        ):
            raise ValueError("履歴の抽せん日範囲がマニフェストと一致しません")
        if draws[482].draw_date != "2022-08-12":
            raise ValueError("第483回の確認済み日付が訂正されていません")
        return {
            "count": len(draws),
            "first_draw": draws[0].draw_no,
            "last_draw": draws[-1].draw_no,
            "sha256": actual_hash,
        }

    def run(self) -> dict[str, Any]:
        """異常なファイル・DB矛盾があればINSERT前に失敗する。"""
        self.validate()
        return Loto7HistoryImporter(self.repo).import_csv(self.source)
