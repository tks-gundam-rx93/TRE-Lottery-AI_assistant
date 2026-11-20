"""クラウドMySQLへのLOTO7履歴CSV一括取込・増分更新CLI。

使い方:
    LOTTERY_MYSQL_URL="mysql://USER:PASSWORD@HOST:3306/tre_lottery" \
    python -m lottery_ai.cloud_import --csv path/to/history.csv

実在するCSVだけを読み込む。ネットワークのアクセス制限を迂回した自動収集は行わない。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import re
from pathlib import Path

from .core import CsvDrawLoader, Draw
from .mysql_repository import MySqlDrawRepository, MySqlSettings


@dataclass(frozen=True)
class ImportPlan:
    """既存DBとの差分。矛盾する番号は無断で上書きしない。"""

    new_draws: tuple[Draw, ...]
    skipped: int
    conflicted: tuple[int, ...]


class Loto7HistoryImporter:
    """CSV検証、データセット差分、原子的一括INSERTを担当するサービス。"""

    def __init__(self, repository: MySqlDrawRepository):
        self.repository = repository

    @staticmethod
    def _canonicalize_date(value: str) -> str:
        """日本語・斜線区切りの抽せん日をISO形式へ統一する。"""
        value = str(value).strip()
        value = value.replace("年", "-").replace("月", "-").replace("日", "")
        value = re.sub(r"\s+", "", value).replace("/", "-").replace(".", "-")
        match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if not match:
            raise ValueError(f"抽せん日の形式が不正です: {value!r}")
        parsed = date(*(int(part) for part in match.groups()))
        if parsed < date(2013, 4, 5) or parsed > date.today():
            raise ValueError(f"抽せん日が不正な範囲です: {parsed.isoformat()}")
        return parsed.isoformat()

    def load_and_validate(self, filename: str | Path) -> list[Draw]:
        """CSVから実データのみ取込。空の抽せん日や未来の日付は拒否する。"""
        loaded = CsvDrawLoader().load(filename)
        return [
            Draw(d.draw_no, self._canonicalize_date(d.draw_date), d.numbers, d.bonus)
            for d in loaded
        ]

    def plan(self, draws: list[Draw]) -> ImportPlan:
        """DBに存在しない回号のみ抽出し、既存回の内容の不一致を検出。"""
        existing = {draw.draw_no: draw for draw in self.repository.all()}
        new = []
        skipped = 0
        conflict = []
        for draw in draws:
            prior = existing.get(draw.draw_no)
            if prior is None:
                new.append(draw)
            elif prior == draw:
                skipped += 1
            else:
                conflict.append(draw.draw_no)
        return ImportPlan(tuple(new), skipped, tuple(conflict))

    def import_csv(self, filename: str | Path, dry_run: bool = False) -> dict:
        """取込対象を集計し、エラーがなければ1トランザクションで登録する。"""
        draws = self.load_and_validate(filename)
        plan = self.plan(draws)
        if plan.conflicted:
            raise ValueError(f"既存DBと抽せん履歴が矛盾する回号: {plan.conflicted[:20]}")
        inserted = 0 if dry_run else self.repository.upsert(list(plan.new_draws), "CSV_MANUAL")
        stats = self.repository.stats()
        return {
            "file": Path(filename).name,
            "dry_run": dry_run, "csv_rows": len(draws),
            "new_rows": len(plan.new_draws),
            "inserted": inserted,
            "skipped": plan.skipped,
            "db_rows": stats["count"],
            "first_draw_in_csv": min(d.draw_no for d in draws),
            "last_draw_in_csv": max(d.draw_no for d in draws),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LOTO7抽せんCSVをクラウドMySQLに増分登録"
    )
    parser.add_argument("--csv", type=Path, required=True, help="実際の抽せん履歴CSV")
    parser.add_argument("--dry-run", action="store_true", help="登録せず重複・差分だけ検査")
    args = parser.parse_args()
    repository = MySqlDrawRepository(MySqlSettings.from_env())
    result = Loto7HistoryImporter(repository).import_csv(args.csv, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
