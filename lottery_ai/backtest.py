"""事後評価。先読みを避け、各回より前の履歴のみで予測する。"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from .core import Draw, HistoryAnalyzer, FrequencyStrategy, GapPairStrategy, MonteCarloStrategy


@dataclass(frozen=True)
class BacktestMetric:
    method: str
    draws: int
    mean_matches: float
    at_least_three: int


class WalkForwardBacktester:
    """統計3方式と同口数の一様ランダムを時系列で比較。"""

    def run(self, history: list[Draw], test_draws: int = 20, samples: int = 500,
            seed: int = 42) -> list[BacktestMetric]:
        ordered = sorted(history, key=lambda d: d.draw_no)
        if len(ordered) < 30 or test_draws < 1 or test_draws > len(ordered) - 20:
            raise ValueError("履歴30回以上、評価回数は過去20回を残す範囲で指定してください")
        if samples < 1:
            raise ValueError("samplesは1以上です")
        result: dict[str, list[int]] = defaultdict(list)
        strategies = [FrequencyStrategy(), GapPairStrategy(), MonteCarloStrategy()]
        for t in range(len(ordered) - test_draws, len(ordered)):
            analyzer = HistoryAnalyzer(ordered[:t])
            actual = set(ordered[t].numbers)
            # 対象回の抽せん結果は候補生成前に参照しない。
            for i, strategy in enumerate(strategies):
                picked = strategy.generate(analyzer, samples, 1, seed + 1000 * t + i)[0]
                result[strategy.name].append(len(actual & set(picked.numbers)))
            rng = random.Random(seed + 1000 * t + 100)
            random_numbers = set(rng.sample(range(1, 38), 7))
            result["RANDOM"].append(len(actual & random_numbers))
        return [BacktestMetric(name, len(hits), sum(hits) / len(hits),
                               sum(x >= 3 for x in hits)) for name, hits in result.items()]