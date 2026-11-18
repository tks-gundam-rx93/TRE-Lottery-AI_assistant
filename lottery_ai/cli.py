"""CLIでCSV取込、番号抽出、3AI判定、バックテストを統合する。"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .agents import OpenAICompatibleClient, ThreeAgentDebate
from .backtest import WalkForwardBacktester
from .core import (CsvDrawLoader, DeepLearningStrategy, FrequencyStrategy,
                   GapPairStrategy, HistoryAnalyzer, MonteCarloStrategy, SqliteDrawRepository)
from .deep import DeepLearningForecaster


def main() -> None:
    parser = argparse.ArgumentParser(description="TRE-Lottery AI Assistant - ロト7分析研究")
    parser.add_argument("--csv", help="履歴CSV（自動Web取得は行わない）")
    parser.add_argument("--db", default="data/lottery.db", help="SQLite保存先")
    parser.add_argument("--samples", type=int, default=2000, help="各戦略の試行回数")
    parser.add_argument("--top", type=int, default=3, help="各方式の候補数")
    parser.add_argument("--seed", type=int, default=42, help="再現用乱数シード")
    parser.add_argument("--with-dl", action="store_true", help="PyTorch学習を追加する")
    parser.add_argument("--judge", choices=["rules", "llm"], default="rules",
                        help="LLMでの真の3AI討論にはAPI接続が必要")
    parser.add_argument("--backtest", type=int, default=0, metavar="N",
                        help="過去N回をウォークフォワード評価")
    parser.add_argument("--output", default="data/candidates.json")
    args = parser.parse_args()

    repo = SqliteDrawRepository(args.db)
    if args.csv:
        imported = repo.upsert(CsvDrawLoader().load(args.csv), "CSV")
        print(f"CSV登録: 新規{imported}件")
    history = repo.all()
    if len(history) < 20:
        parser.error("20回以上の履歴を--csvで登録してください")

    if args.backtest:
        metrics = WalkForwardBacktester().run(history, args.backtest,
                                               max(100, args.samples // 4), args.seed)
        for m in metrics:
            print(f"BACKTEST {m.method}: {m.draws}回 平均一致{m.mean_matches:.3f}個 3個以上{m.at_least_three}回")

    analyzer = HistoryAnalyzer(history)
    strategies = [FrequencyStrategy(), GapPairStrategy(), MonteCarloStrategy()]
    report = None
    if args.with_dl:
        forecaster = DeepLearningForecaster(args.seed)
        report = forecaster.fit(history)
        strategies.append(DeepLearningStrategy(forecaster.predict(history)))
        print(f"深層学習: 検証BCE={report.validation_bce} 一様基準BCE={report.random_baseline_bce}")

    pool = []
    for idx, strategy in enumerate(strategies):
        pool.extend(strategy.generate(analyzer, args.samples, args.top, args.seed + idx))
    client = OpenAICompatibleClient() if args.judge == "llm" else None
    debate = ThreeAgentDebate(client).run(pool, history)
    output = {"lottery_type": "LOTO7", "source_last_draw": history[-1].draw_no,
              "target_draw": history[-1].draw_no + 1,
              "warning": "どの7数字も公平抽せんでの1等確率は等しい。スコアや得票は確率ではない。",
              "candidates": [c.as_dict() for c in pool], "debate": debate.as_dict(),
              "training": asdict(report) if report else None}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    winning = next(c for c in pool if c.candidate_id == debate.winner_id)
    print(f"判定モード: {debate.mode} / 選定候補: {winning.candidate_id} {winning.numbers}")
    print(f"JSON出力: {target}")


if __name__ == "__main__":
    main()